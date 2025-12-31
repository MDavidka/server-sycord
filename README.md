# server-sycord

A Flask server that automatically deploys content from MongoDB to Cloudflare Pages using Wrangler CLI.

## Features

- 🚀 RESTful API for triggering deployments
- 📦 Retrieves files from MongoDB
- ☁️ Deploys to Cloudflare Pages using Wrangler
- 🎨 Modern styled web interface
- 🔒 Environment-based configuration
- 📊 Health check endpoint

## Prerequisites

- Python 3.8 or higher
- MongoDB instance
- Cloudflare account with API token
- Node.js and npm (for Wrangler CLI)
- Wrangler CLI installed globally: `npm install -g wrangler`

## Installation

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
- `MONGO_DB`: Database name
- `MONGO_COLLECTION`: Collection name containing files
- `CLOUDFLARE_API_TOKEN`: Your Cloudflare API token
- `CLOUDFLARE_ACCOUNT_ID`: Your Cloudflare account ID (optional)
- `CLOUDFLARE_PROJECT_NAME`: Your Cloudflare Pages project name

## MongoDB Document Structure

Files in MongoDB should have the following structure:

```json
{
  "filename": "index.html",
  "content": "<!DOCTYPE html><html>...</html>"
}
```

## Usage

### Running the Server

Start the Flask server:

```bash
python app.py
```

The server will start on `http://localhost:5000` by default.

### Using with Gunicorn (Production)

For production, use Gunicorn:

```bash
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

## API Endpoints

### POST /api/deploy

Triggers a deployment to Cloudflare Pages.

**Request:**
```bash
curl -X POST http://localhost:5000/api/deploy
```

**Response (Success):**
```json
{
  "success": true,
  "message": "Deployment successful",
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
  "service": "Cloudflare Pages Deployment Server"
}
```

## Web Interface

Visit `http://localhost:5000` in your browser to access the modern styled waiting page with a deployment trigger button.

## Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `MONGO_URI` | MongoDB connection string | No | `mongodb://localhost:27017/` |
| `MONGO_DB` | MongoDB database name | No | `sycord_db` |
| `MONGO_COLLECTION` | MongoDB collection name | No | `files` |
| `CLOUDFLARE_API_TOKEN` | Cloudflare API token | Yes | - |
| `CLOUDFLARE_ACCOUNT_ID` | Cloudflare account ID | No | - |
| `CLOUDFLARE_PROJECT_NAME` | Cloudflare Pages project name | Yes | - |
| `PORT` | Server port | No | `5000` |
| `DEBUG` | Enable Flask debug mode | No | `False` |

## Deployment Flow

1. API request received at `/api/deploy`
2. Server connects to MongoDB
3. Retrieves all files from the specified collection
4. Saves files to a temporary directory
5. Executes `wrangler pages deploy` command
6. Uploads files to Cloudflare Pages
7. Cleans up temporary directory
8. Returns deployment result

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

### Cloudflare deployment failed
- Verify your `CLOUDFLARE_API_TOKEN` has the correct permissions
- Check that `CLOUDFLARE_PROJECT_NAME` matches your Cloudflare Pages project
- Review Wrangler logs in the API response

## License

MIT

## Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.