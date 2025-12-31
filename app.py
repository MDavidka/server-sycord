import os
import subprocess
import tempfile
import shutil
from flask import Flask, render_template, request, jsonify
from pymongo import MongoClient
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
MONGO_DB = os.getenv('MONGO_DB', 'sycord_db')
MONGO_COLLECTION = os.getenv('MONGO_COLLECTION', 'files')

# Cloudflare configuration
CLOUDFLARE_API_TOKEN = os.getenv('CLOUDFLARE_API_TOKEN')
CLOUDFLARE_ACCOUNT_ID = os.getenv('CLOUDFLARE_ACCOUNT_ID')
CLOUDFLARE_PROJECT_NAME = os.getenv('CLOUDFLARE_PROJECT_NAME')


def sanitize_filename(filename):
    """Sanitize filename to prevent path traversal attacks"""
    if not filename:
        return 'index.html'
    
    # Normalize path separators to forward slashes for consistent checking
    normalized = filename.replace('\\', '/')
    
    # Reject absolute paths (both Unix and Windows styles)
    if os.path.isabs(filename) or filename.startswith('/') or (len(filename) > 1 and filename[1] == ':'):
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
    if '..' in safe_filename.split(os.sep):
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
            except (UnicodeEncodeError, UnicodeDecodeError) as e:
                logger.error(f"Encoding error for file {filename}: {e}")
                # Try with error handling for invalid characters
                with open(file_path, 'w', encoding='utf-8', errors='replace') as f:
                    f.write(content)
                logger.info(f"Saved file with encoding fallback: {filename}")
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


@app.route('/api/deploy', methods=['POST'])
def deploy():
    """API endpoint to trigger deployment"""
    try:
        logger.info("Received deployment request")
        
        # Retrieve files from MongoDB
        files = retrieve_files_from_mongo()
        
        if not files:
            return jsonify({
                'success': False,
                'message': 'No files found in MongoDB'
            }), 404
        
        # Save files to temporary directory
        temp_dir = save_files_to_temp_directory(files)
        
        try:
            # Deploy to Cloudflare Pages
            result = deploy_to_cloudflare(temp_dir)
            
            if result['success']:
                return jsonify({
                    'success': True,
                    'message': 'Deployment successful',
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
        'service': 'Cloudflare Pages Deployment Server'
    }), 200


if __name__ == '__main__':
    # Check if required environment variables are set
    if not CLOUDFLARE_API_TOKEN:
        logger.warning("CLOUDFLARE_API_TOKEN not set. Deployment will fail.")
    
    if not CLOUDFLARE_PROJECT_NAME:
        logger.warning("CLOUDFLARE_PROJECT_NAME not set. Deployment will fail.")
    
    # Run Flask app
    port = int(os.getenv('PORT', 5000))
    debug = os.getenv('DEBUG', 'False').lower() == 'true'
    
    logger.info(f"Starting Flask server on port {port}")
    app.run(host='0.0.0.0', port=port, debug=debug)
