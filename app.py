import os
import re
import subprocess
import tempfile
import shutil
import requests
from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
from bson import ObjectId
from bson.errors import InvalidId
from dotenv import load_dotenv
import logging
from pathlib import Path

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# MongoDB configuration
MONGO_URI = os.getenv('MONGO_URI', 'mongodb://localhost:27017/')
MONGO_DB = os.getenv('MONGO_DB', 'test')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'github_tokens')

# Cloudflare configuration
CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
CLOUDFLARE_PROJECT_NAME = os.getenv('CLOUDFLARE_PROJECT_NAME')

# Project ID for GitHub token lookup
PROJECT_ID = os.getenv('PROJECT_ID', '')

# API timeout configuration (in seconds)
API_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 120


def sanitize_project_name(name):
    """Sanitize a repository name for use as a Cloudflare project name"""
    if not name:
        return 'unnamed-project'
    # Replace any non-alphanumeric characters (except hyphens) with hyphens
    sanitized = re.sub(r'[^a-zA-Z0-9-]', '-', name.lower())
    # Cloudflare project names have a max length of 63 characters
    return sanitized[:63]


def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks"""
    if not filename:
        return 'index.html'
    
    # Normalize path separators to forward slashes for consistent checking
    normalized = filename.replace('\\', '/')
    
    # Reject absolute paths
    if os.path.isabs(filename) or filename.startswith('/'):
        logger.warning(f"Rejected absolute path: {filename}")
        return os.path.basename(normalized)
    
    # Reject paths that try to go up directories
    if (normalized.startswith('..') or 
        '/..' in normalized or 
        normalized.endswith('/..')):
        logger.warning(f"Rejected path traversal attempt: {filename}")
        return os.path.basename(normalized)
    
    # Use normpath after validation to clean up the path
    safe_filename = os.path.normpath(normalized)
    
    # Final check: ensure no '..' components remain after normalization
    # Split by os.sep since normpath converts to os-specific separators
    path_parts = safe_filename.split(os.sep)
    if '..' in path_parts:
        logger.warning(f"Rejected path with '..' after normalization: {filename}")
        return os.path.basename(normalized)
    
    return safe_filename


def get_mongo_client():
    """Create and return MongoDB client"""
    try:
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        # Test connection
        client.server_info()
        return client
    except Exception as e:
        logger.error(f"Failed to connect to MongoDB: {e}")
        raise


def get_github_token_from_mongo():
    """Retrieve GitHub token from MongoDB based on project ID"""
    try:
        client = get_mongo_client()
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        # Find the document with the project ID
        doc = collection.find_one({'_id': ObjectId(PROJECT_ID)})
        
        if doc and 'token' in doc:
            logger.info("Retrieved GitHub token from MongoDB")
            return doc['token']
        
        # Also try looking for github_token field
        if doc and 'github_token' in doc:
            logger.info("Retrieved GitHub token from MongoDB")
            return doc['github_token']
            
        logger.warning("GitHub token not found in MongoDB document")
        return None
    except Exception as e:
        logger.error(f"Error retrieving GitHub token from MongoDB: {e}")
        return None
    finally:
        if 'client' in locals():
            client.close()


def get_repository_projection(include_tokens=False):
    """Build MongoDB projection for repository documents"""
    projection = {
        'owner': 1,
        'repo': 1,
        'name': 1,
        'description': 1,
        'default_branch': 1,
        'private': 1
    }
    if include_tokens:
        projection.update({'token': 1, 'github_token': 1})
    return projection


def get_repository_documents(include_tokens=False):
    """Retrieve repository documents (owner/repo/token) from MongoDB"""
    try:
        client = get_mongo_client()
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        projection = get_repository_projection(include_tokens)
        docs = list(collection.find({}, projection))
        logger.info(f"Retrieved {len(docs)} repository documents from MongoDB")
        return docs
    except Exception as e:
        logger.error(f"Error retrieving repository documents from MongoDB: {e}")
        raise
    finally:
        if 'client' in locals():
            client.close()


def get_repository_document_by_id(repo_id, include_tokens=False):
    """Retrieve a single repository document by its ID"""
    try:
        client = get_mongo_client()
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        projection = get_repository_projection(include_tokens)
        
        try:
            object_id = ObjectId(repo_id)
        except (InvalidId, TypeError):
            logger.warning(f"Invalid repository id: {repo_id}")
            return None
        
        doc = collection.find_one({'_id': object_id}, projection)
        return doc
    except Exception as e:
        logger.error(f"Error retrieving repository document from MongoDB: {e}")
        raise
    finally:
        if 'client' in locals():
            client.close()


def get_repository_name(repo_doc):
    """Extract repository name (prefer new 'repo' field, fall back to legacy 'name' field). Returns None if neither is set."""
    return repo_doc.get('repo') or repo_doc.get('name')


def get_repository_token(repo_doc):
    """Return repository token, preferring 'token' and falling back to legacy 'github_token'. Returns None if neither exists."""
    return repo_doc.get('token') or repo_doc.get('github_token')


def get_github_repositories(github_token):
    """Fetch repositories from GitHub using the token"""
    if not github_token:
        logger.error("No GitHub token provided")
        return []
    
    try:
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        response = requests.get(
            'https://api.github.com/user/repos',
            headers=headers,
            params={'per_page': 100, 'sort': 'updated'},
            timeout=API_TIMEOUT
        )
        
        if response.status_code == 200:
            repos = response.json()
            logger.info(f"Fetched {len(repos)} repositories from GitHub")
            return repos
        else:
            logger.error(f"GitHub API error: {response.status_code} - {response.text}")
            return []
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching GitHub repositories: {e}")
        return []


def download_github_repo(github_token, repo_full_name, branch='main'):
    """Download a GitHub repository to a temporary directory"""
    temp_dir = tempfile.mkdtemp(prefix='github_repo_')
    logger.info(f"Created temporary directory for repo: {temp_dir}")
    
    try:
        # Try to download the repository as a zip archive
        headers = {
            'Authorization': f'token {github_token}',
            'Accept': 'application/vnd.github.v3+json'
        }
        
        # First, try main branch, then master if main fails
        branches_to_try = [branch, 'main', 'master']
        
        for try_branch in branches_to_try:
            url = f'https://api.github.com/repos/{repo_full_name}/zipball/{try_branch}'
            response = requests.get(url, headers=headers, stream=True, timeout=DOWNLOAD_TIMEOUT)
            
            if response.status_code == 200:
                # Save the zip file
                zip_path = os.path.join(temp_dir, 'repo.zip')
                with open(zip_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                # Extract the zip file
                import zipfile
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    zip_ref.extractall(temp_dir)
                
                # Remove the zip file
                os.remove(zip_path)
                
                # Find the extracted directory (GitHub adds a prefix)
                extracted_dirs = [d for d in os.listdir(temp_dir) 
                                if os.path.isdir(os.path.join(temp_dir, d))]
                
                if extracted_dirs:
                    # Move contents from extracted dir to temp_dir
                    extracted_path = os.path.join(temp_dir, extracted_dirs[0])
                    for item in os.listdir(extracted_path):
                        src = os.path.join(extracted_path, item)
                        dst = os.path.join(temp_dir, item)
                        shutil.move(src, dst)
                    os.rmdir(extracted_path)
                
                logger.info(f"Downloaded repository {repo_full_name} from branch {try_branch}")
                return temp_dir
        
        # If all branches fail
        logger.error(f"Failed to download repository {repo_full_name}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None
        
    except Exception as e:
        logger.error(f"Error downloading repository: {e}")
        shutil.rmtree(temp_dir, ignore_errors=True)
        return None


def create_cloudflare_project(project_name):
    """Create a new Cloudflare Pages project"""
    if not CLOUDFLARE_API_TOKEN or not CLOUDFLARE_ACCOUNT_ID:
        logger.error("Cloudflare credentials not configured")
        return None
    
    try:
        headers = {
            'Authorization': f'Bearer {CLOUDFLARE_API_TOKEN}',
            'Content-Type': 'application/json'
        }
        
        # Create project using Cloudflare API
        url = f'https://api.cloudflare.com/client/v4/accounts/{CLOUDFLARE_ACCOUNT_ID}/pages/projects'
        
        payload = {
            'name': project_name,
            'production_branch': 'main'
        }
        
        response = requests.post(url, headers=headers, json=payload, timeout=API_TIMEOUT)
        
        if response.status_code in [200, 201]:
            result = response.json()
            if result.get('success'):
                logger.info(f"Created Cloudflare project: {project_name}")
                return result.get('result')
            else:
                logger.error(f"Cloudflare API error: {result.get('errors')}")
                return None
        elif response.status_code == 409:
            # Project already exists
            logger.info(f"Cloudflare project already exists: {project_name}")
            return {'name': project_name}
        else:
            logger.error(f"Cloudflare API error: {response.status_code} - {response.text}")
            return None
    except requests.exceptions.RequestException as e:
        logger.error(f"Error creating Cloudflare project: {e}")
        return None


def deploy_to_cloudflare_pages(directory_path, project_name):
    """Deploy files to Cloudflare Pages using wrangler"""
    if not CLOUDFLARE_API_TOKEN:
        raise ValueError("CLOUDFLARE_API_TOKEN not set in environment variables")
    
    try:
        # Set environment variables for wrangler
        env = os.environ.copy()
        env['CLOUDFLARE_API_TOKEN'] = CLOUDFLARE_API_TOKEN
        if CLOUDFLARE_ACCOUNT_ID:
            env['CLOUDFLARE_ACCOUNT_ID'] = CLOUDFLARE_ACCOUNT_ID
        
        # Run wrangler pages deploy command
        cmd = [
            'wrangler',
            'pages',
            'deploy',
            directory_path,
            '--project-name',
            project_name,
            '--branch',
            'main'
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            logger.info("Deployment successful")
            logger.info(result.stdout)

            # Extract URL from stdout
            # Wrangler output typically contains: "Take a peek over at https://<project>.pages.dev"
            # or just the URL at the end.
            url = None
            # Search for https://*.pages.dev
            url_match = re.search(r'https://[a-zA-Z0-9-]+\.pages\.dev', result.stdout)
            if url_match:
                url = url_match.group(0)

            return {
                'success': True,
                'output': result.stdout,
                'url': url,
                'error': None
            }
        else:
            logger.error(f"Deployment failed: {result.stderr}")
            return {
                'success': False,
                'output': result.stdout,
                'error': result.stderr
            }
    except subprocess.TimeoutExpired:
        logger.error("Deployment timed out")
        return {
            'success': False,
            'output': None,
            'error': 'Deployment timed out after 5 minutes'
        }
    except FileNotFoundError:
        logger.error("wrangler command not found")
        return {
            'success': False,
            'output': None,
            'error': 'wrangler CLI not found. Please install it: npm install -g wrangler'
        }
    except Exception as e:
        logger.error(f"Deployment error: {e}")
        return {
            'success': False,
            'output': None,
            'error': str(e)
        }


def retrieve_files_from_mongo():
    """Retrieve files from MongoDB"""
    try:
        client = get_mongo_client()
        db = client[MONGO_DB]
        collection = db[MONGO_COLLECTION]
        
        files = list(collection.find({}))
        logger.info(f"Retrieved {len(files)} files from MongoDB")
        
        return files
    except Exception as e:
        logger.error(f"Error retrieving files from MongoDB: {e}")
        raise
    finally:
        if 'client' in locals():
            client.close()


def save_files_to_temp_directory(files):
    """Save MongoDB files to a temporary directory"""
    temp_dir = tempfile.mkdtemp(prefix='cloudflare_deploy_')
    logger.info(f"Created temporary directory: {temp_dir}")
    
    try:
        for file_doc in files:
            # Assume files have 'filename' and 'content' fields
            raw_filename = file_doc.get('filename', 'index.html')
            content = file_doc.get('content', '')
            
            # Sanitize filename to prevent path traversal
            filename = sanitize_filename(raw_filename)
            
            file_path = os.path.join(temp_dir, filename)
            
            # Ensure the resolved path is still within temp_dir
            real_path = os.path.realpath(file_path)
            real_temp_dir = os.path.realpath(temp_dir)
            if not real_path.startswith(real_temp_dir):
                logger.warning(f"Rejected file path outside temp directory: {raw_filename}")
                continue
            
            # Create subdirectories if needed
            dir_path = os.path.dirname(file_path)
            if dir_path and dir_path != temp_dir:
                # Verify directory path is still within temp_dir
                real_dir_path = os.path.realpath(dir_path)
                if not real_dir_path.startswith(real_temp_dir):
                    logger.warning(f"Rejected directory path outside temp directory: {raw_filename}")
                    continue
                os.makedirs(dir_path, exist_ok=True)
            
            # Write content to file with error handling
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(content)
                logger.info(f"Saved file: {filename}")
            except UnicodeEncodeError as e:
                # Content from MongoDB contains characters that cannot be encoded to UTF-8
                logger.error(f"UTF-8 encoding error for file {filename}: {e}")
                logger.warning(f"Skipping file {filename} due to encoding issues")
                continue
            except Exception as e:
                logger.error(f"Failed to write file {filename}: {e}")
                continue
        
        return temp_dir
    except Exception as e:
        # Clean up temp directory on error
        shutil.rmtree(temp_dir, ignore_errors=True)
        raise


def deploy_to_cloudflare(directory_path):
    """Deploy files to Cloudflare Pages using wrangler"""
    if not CLOUDFLARE_API_TOKEN:
        raise ValueError("CLOUDFLARE_API_TOKEN not set in environment variables")
    
    if not CLOUDFLARE_PROJECT_NAME:
        raise ValueError("CLOUDFLARE_PROJECT_NAME not set in environment variables")
    
    try:
        # Set environment variables for wrangler
        env = os.environ.copy()
        env['CLOUDFLARE_API_TOKEN'] = CLOUDFLARE_API_TOKEN
        if CLOUDFLARE_ACCOUNT_ID:
            env['CLOUDFLARE_ACCOUNT_ID'] = CLOUDFLARE_ACCOUNT_ID
        
        # Run wrangler pages deploy command
        cmd = [
            'wrangler',
            'pages',
            'deploy',
            directory_path,
            '--project-name',
            CLOUDFLARE_PROJECT_NAME
        ]
        
        logger.info(f"Running command: {' '.join(cmd)}")
        
        result = subprocess.run(
            cmd,
            env=env,
            capture_output=True,
            text=True,
            timeout=300  # 5 minutes timeout
        )
        
        if result.returncode == 0:
            logger.info("Deployment successful")
            logger.info(result.stdout)
            return {
                'success': True,
                'output': result.stdout,
                'error': None
            }
        else:
            logger.error(f"Deployment failed: {result.stderr}")
            return {
                'success': False,
                'output': result.stdout,
                'error': result.stderr
            }
    except subprocess.TimeoutExpired:
        logger.error("Deployment timed out")
        return {
            'success': False,
            'output': None,
            'error': 'Deployment timed out after 5 minutes'
        }
    except FileNotFoundError:
        logger.error("wrangler command not found")
        return {
            'success': False,
            'output': None,
            'error': 'wrangler CLI not found. Please install it: npm install -g wrangler'
        }
    except Exception as e:
        logger.error(f"Deployment error: {e}")
        return {
            'success': False,
            'output': None,
            'error': str(e)
        }


@app.route('/')
def index():
    """Render the main waiting page"""
    return render_template('index.html')


@app.route('/api/repos', methods=['GET'])
def get_repos():
    """API endpoint to fetch GitHub repositories"""
    try:
        logger.info("Fetching GitHub repositories")
        
        # Get repository documents from MongoDB
        repo_docs = get_repository_documents()
        
        if not repo_docs:
            return jsonify({
                'success': True,
                'message': 'No repositories found in database',
                'repositories': []
            }), 200
        
        # Format repositories for frontend
        formatted_repos = []
        for repo_doc in repo_docs:
            repo_name = get_repository_name(repo_doc)
            owner = repo_doc.get('owner')
            
            if not owner or not repo_name:
                logger.warning(f"Skipping repository document missing owner or name: {repo_doc.get('_id')}")
                continue
            
            formatted_repos.append({
                'id': str(repo_doc.get('_id')),
                'name': repo_name,
                'full_name': f"{owner}/{repo_name}",
                'description': repo_doc.get('description', ''),
                'default_branch': repo_doc.get('default_branch', 'main'),
                'private': repo_doc.get('private', False)
            })
        
        return jsonify({
            'success': True,
            'repositories': formatted_repos
        }), 200
        
    except Exception as e:
        logger.error(f"Error fetching repositories: {e}")
        return jsonify({
            'success': False,
            'message': 'Failed to fetch repositories',
            'error': str(e),
            'repositories': []
        }), 500


@app.route('/api/deploy', methods=['POST'])
def deploy():
    """API endpoint to trigger deployment from GitHub repository"""
    try:
        logger.info("Received deployment request")
        
        # Get request data
        data = request.get_json() or {}
        repo_id = data.get('repo_id')
        
        if not repo_id:
            return jsonify({
                'success': False,
                'message': 'Repository ID is required'
            }), 400
        
        # Get repository details from MongoDB
        selected_repo = get_repository_document_by_id(repo_id, include_tokens=True)
        
        if not selected_repo:
            return jsonify({
                'success': False,
                'message': 'Repository configuration not found'
            }), 404
        
        github_token = get_repository_token(selected_repo)
        
        if not github_token:
            return jsonify({
                'success': False,
                'message': 'GitHub token not found for repository'
            }), 404
        
        owner = selected_repo.get('owner')
        repo_name = get_repository_name(selected_repo)
        
        if not owner or not repo_name:
            return jsonify({
                'success': False,
                'message': 'Repository configuration missing owner or name'
            }), 400
        
        default_branch = selected_repo.get('default_branch', 'main')
        repo_full_name = f"{owner}/{repo_name}"
        
        # Generate Cloudflare project name from repo name (sanitized)
        cf_project_name = sanitize_project_name(repo_name)
        
        # Create Cloudflare project if it doesn't exist
        create_cloudflare_project(cf_project_name)
        
        # Download repository from GitHub
        temp_dir = download_github_repo(github_token, repo_full_name, default_branch)
        
        if not temp_dir:
            return jsonify({
                'success': False,
                'message': 'Failed to download repository from GitHub'
            }), 500
        
        try:
            # Deploy to Cloudflare Pages
            result = deploy_to_cloudflare_pages(temp_dir, cf_project_name)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': f'Deployment successful! Project: {cf_project_name}',
                    'project_name': cf_project_name,
                    'url': result.get('url'),
                    'output': result['output']
                }), 200
            else:
                return jsonify({
                    'success': False,
                    'message': 'Deployment failed',
                    'error': result['error']
                }), 500
        finally:
            # Clean up temporary directory
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info(f"Cleaned up temporary directory: {temp_dir}")
    
    except Exception as e:
        logger.error(f"Deployment error: {e}")
        return jsonify({
            'success': False,
            'message': 'Deployment failed',
            'error': str(e)
        }), 500


@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'healthy',
        'service': 'M1 Instance - Sycord Deployment Server',
        'instance': 'M1'
    }), 200


if __name__ == '__main__':
    # Check if required environment variables are set or still at defaults
    config_errors = []

    # Check for empty values
    if not CLOUDFLARE_API_TOKEN:
        config_errors.append("CLOUDFLARE_API_TOKEN not set")

    # Check for default values
    defaults = {
        "CLOUDFLARE_API_TOKEN": "your_cloudflare_api_token",
        "CLOUDFLARE_ACCOUNT_ID": "your_cloudflare_account_id",
        "MONGO_URI": "mongodb+srv://user:password@cluster.mongodb.net/?appName=Cluster"
    }

    for key, default_val in defaults.items():
        val = os.getenv(key)
        if val == default_val:
            config_errors.append(f"{key} is still set to the default placeholder: '{default_val}'")

    if config_errors:
        logger.error("Configuration Error: The application is not properly configured.")
        for error in config_errors:
            logger.error(f"- {error}")
        logger.error("Please edit the .env file with your actual credentials.")
        exit(1)
    
    if not CLOUDFLARE_PROJECT_NAME:
        logger.warning("CLOUDFLARE_PROJECT_NAME not set. Deployment will fail.")
    
    # Run Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
