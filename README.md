# server-sycord

A Flask server (M1 Instance) that automatically deploys content from GitHub repositories to Cloudflare Pages using Wrangler CLI.

![Desktop UI](https://github.com/user-attachments/assets/abaf97f9-b1e3-431c-87a0-5040112eca2f)

## Features

- 🚀 RESTful API for triggering deployments
- 🔗 GitHub integration - fetches repositories using stored GitHub tokens
- ☁️ Deploys to Cloudflare Pages using Wrangler
- 🎨 Modern dark UI with Inter font (#19191B theme)
- 📱 Mobile-optimized responsive design
- 🔄 Real-time data sync visualization
- 🔒 Environment-based configuration
- 📊 Health check endpoint

## Prerequisites

- Python 3.8 or higher
- MongoDB instance with GitHub tokens stored
- Cloudflare account with API token
- Node.js and npm (for Wrangler CLI)
- Wrangler CLI installed globally: `npm install -g wrangler`

## Quick Start

Use the auto-deploy starter script:

```bash
chmod +x starter.sh
./starter.sh
```

This script will:
1. Check and install Node.js if needed
2. Install Wrangler CLI globally
3. Set up Python virtual environment
4. Install Python dependencies
5. Start the deployment server

## Manual Installation

1. Clone the repository:
```bash
git clone https://github.com/MDavidka/server-sycord.git
cd server-sycord
```

2. Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install Python dependencies:
```bash
pip install -r requirements.txt
```

4. Install Wrangler CLI:
```bash
npm install -g wrangler
```

5. Configure environment variables:
```bash
cp .env.example .env
```

Edit `.env` and set your configuration:
- `MONGO_URI`: MongoDB connection string
- `MONGO_DB`: Database name (default: `test`)
- `MONGO_COLLECTION`: Collection name (default: `github_tokens`)
- `PROJECT_ID`: MongoDB ObjectId for GitHub token lookup
- `CLOUDFLARE_API_TOKEN`: Your Cloudflare API token
- `CLOUDFLARE_ACCOUNT_ID`: Your Cloudflare account ID

## MongoDB Document Structure

GitHub repositories should be stored in MongoDB with the following structure:

```json
{
  "_id": ObjectId("6954ed250d9fa1238cb13e3c"),
  "owner": "your-github-username",
  "repo": "your-repository",
  "token": "github_personal_access_token",
  "default_branch": "main"
}
```

Use the `token` field for new documents. A legacy `github_token` field is also accepted for backward compatibility. The server will use `token` when it is set, otherwise it will fall back to `github_token`.

The preferred repository field is `repo`. A legacy `name` field is also honored for backward compatibility when `repo` is not present.

## Usage

### Running the Server

Start the Flask server:

```bash
python app.py
```

Or use the starter script:

```bash
./starter.sh
```

The server will start on `http://localhost:5000` by default.

### Using with Gunicorn (Production)

For production, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API Endpoints

### GET /api/repos

Fetch GitHub repositories stored in MongoDB (one document per repository).

**Request:**
```bash
curl http://localhost:5000/api/repos
```

**Response:**
```json
{
  "success": true,
  "repositories": [
    {
      "id": "123456789",
      "name": "my-repo",
      "full_name": "username/my-repo",
      "description": "Repository description",
      "default_branch": "main",
      "private": false
    }
  ]
}
```

### POST /api/deploy

Triggers a deployment from a GitHub repository to Cloudflare Pages.

**Request:**
```bash
curl -X POST http://localhost:5000/api/deploy \
  -H "Content-Type: application/json" \
  -d '{"repo_id": "123456789"}'
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Deployment successful! Project: my-repo",
  "project_name": "my-repo",
  "output": "..."
}
```

**Response (Error):**
```json
{
  "success": false,
  "message": "Deployment failed",
  "error": "Error details..."
}
```

### GET /api/health

Health check endpoint.

**Request:**
```bash
curl http://localhost:5000/api/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "M1 Instance - Sycord Deployment Server",
  "instance": "M1"
}
```

## Web Interface

Visit `http://localhost:5000` in your browser to access the modern dark-themed UI with:
- M1 Instance branding
- Real-time data sync visualization (GitHub → Cloudflare)
- Repository selection
- One-click deployment

### Mobile View

![Mobile UI](https://github.com/user-attachments/assets/7377a3d3-5477-4948-a1ef-9616933a6faa)

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MONGO_URI` | MongoDB connection string | No | `mongodb://localhost:27017/` |
| `MONGO_DB` | MongoDB database name | No | `test` |
| `MONGO_COLLECTION` | MongoDB collection name | No | `github_tokens` |
| `PROJECT_ID` | MongoDB ObjectId for token lookup | No | `6954ed250d9fa1238cb13e3c` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token | Yes | - |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID | Yes | - |
| `PORT` | Server port | No | `5000` |
| `DEBUG` | Enable Flask debug mode | No | `False` |

## Deployment Flow

1. User selects a repository from the UI
2. Server retrieves GitHub token from MongoDB
3. Downloads repository from GitHub as a zip archive
4. Extracts files to a temporary directory
5. Creates a new Cloudflare Pages project (if needed)
6. Executes `wrangler pages deploy` command
7. Uploads files to Cloudflare Pages
8. Cleans up temporary directory
9. Returns deployment result

## Troubleshooting

### Wrangler not found
Ensure Wrangler is installed globally:
```bash
npm install -g wrangler
```

### MongoDB connection failed
Verify your `MONGO_URI` is correct and MongoDB is running:
```bash
mongosh "your-mongo-uri"
```

### GitHub token not found
Ensure the `PROJECT_ID` matches an existing document in your MongoDB collection with a `token` or `github_token` field.

### Cloudflare deployment failed
- Verify your `CLOUDFLARE_API_TOKEN` has the correct permissions
- Check that `CLOUDFLARE_ACCOUNT_ID` is correct
- Review Wrangler logs in the API response

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.
