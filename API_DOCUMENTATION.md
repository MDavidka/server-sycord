# Sycord Deployment Server - API Documentation

This document provides detailed information about the deployment API endpoints, including request/response formats, expected parameters, and what the API provides.

## Table of Contents

1. [Database Structure](#database-structure)
2. [API Endpoints](#api-endpoints)
   - [Deploy by Username and Repo ID](#deploy-by-username-and-repo-id)
   - [List All Repositories](#list-all-repositories)
   - [List User Repositories](#list-user-repositories)
   - [Get Deployment Domain by Repo ID](#get-deployment-domain-by-repo-id)
   - [Health Check](#health-check)
   - [Get Recent Logs](#get-recent-logs)
3. [Error Handling](#error-handling)
4. [Deployment Flow](#deployment-flow)

---

## Database Structure

The API expects repositories to be stored in MongoDB with the following structure:

**Database:** `main`  
**Collection:** `users`  
**Path:** `main > users > {username} > git_connection > {repo_id: {repo document}}`

### User Document Schema

```json
{
  "_id": ObjectId("..."),
  "username": "MDavidka",
  "git_connection": {
    "1126661988": {
      "username": "MDavidka",
      "repo_id": "1126661988",
      "git_url": "https://github.com/MDavidka/tesf",
      "git_token": "ghp_xxxxxxxxxxxxxxxxxxxx",
      "repo_name": "tesf",
      "project_id": "6957a3fb538e5f68b68b58f7",
      "deployed_at": {
        "$date": "2026-01-02T10:56:42.117Z"
      }
    }
  }
}
```

Note: `git_connection` is a **dictionary/object** where keys are the `repo_id` values and values are the repository documents.

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | The username of the repository owner in the system |
| `repo_id` | string | Yes | A unique numeric identifier for the repository (e.g., "1126661988") |
| `git_url` | string | Yes | The GitHub repository URL in HTTPS format (e.g., `https://github.com/owner/repo`) |
| `git_token` | string | Yes | GitHub personal access token with `repo` scope for accessing the repository |
| `repo_name` | string | No | The repository name (optional, can be parsed from git_url) |
| `project_id` | string | No | The Cloudflare project ID after deployment |
| `deployed_at` | date | No | Timestamp of the last deployment |

---

## API Endpoints

### Deploy by Repo ID

**Endpoint:** `GET/POST /api/deploy/{repo_id}`

This is the primary deployment endpoint that triggers a deployment from a GitHub repository to Cloudflare Pages using only the repository ID.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `repo_id` | string | Yes | Numeric repository identifier |

#### What the API Expects

1. **Valid `repo_id`** - Must be a numeric string
2. **Repository document** - Must contain `git_url` and `git_token`

#### Request Examples

```bash
# Using GET request
curl "http://localhost:5000/api/deploy/1126661988"

# Using POST request
curl -X POST "http://localhost:5000/api/deploy/1126661988"

# Using POST with headers (no body required)
curl -X POST "http://localhost:5000/api/deploy/1126661988" \
  -H "Accept: application/json"
```

#### What the API Provides

The API performs the following actions:

1. **Validation**
   - Validates that `repo_id` is a numeric string
   - Verifies the repository entry exists in `git_connection`

2. **Repository Retrieval**
   - Fetches `git_url` and `git_token` from the database
   - Parses the `git_url` to extract owner and repository name

3. **GitHub Download**
   - Downloads the repository as a ZIP archive using the GitHub API
   - Authenticates using the `git_token`
   - Tries multiple branches: specified branch → `main` → `master`

4. **Cloudflare Deployment**
   - Creates a Cloudflare Pages project (if it doesn't exist)
   - Deploys the repository files using Wrangler CLI
   - Returns the live deployment URL

#### Response Format (Success)

```json
{
  "success": true,
  "message": "Deployment successful! Project: tesf",
  "project_name": "tesf",
  "url": "https://tesf.pages.dev",
  "username": "MDavidka",
  "repo_id": "1126661988",
  "output": "Wrangler CLI output..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `success` | boolean | Always `true` for successful deployments |
| `message` | string | Human-readable success message |
| `project_name` | string | Sanitized Cloudflare project name |
| `url` | string | Live deployment URL on Cloudflare Pages |
| `username` | string | The username that was provided |
| `repo_id` | string | The repo_id that was provided |
| `output` | string | Raw output from Wrangler CLI |

#### Response Format (Error)

```json
{
  "success": false,
  "message": "Error description",
  "error": "Detailed error information (optional)"
}
```

#### Error Codes

| HTTP Status | Message | Cause |
|-------------|---------|-------|
| 400 | Invalid repo_id format. Expected numeric identifier. | `repo_id` is not numeric |
| 404 | Repository {repo_id} not found for user {username} | User or repository doesn't exist |
| 404 | GitHub token (git_token) not found for repository | Missing `git_token` in database |
| 404 | Git URL (git_url) not found for repository | Missing `git_url` in database |
| 400 | Could not parse git_url: {url} | Invalid GitHub URL format |
| 500 | Failed to download repository from GitHub | GitHub API error or invalid token |
| 500 | Deployment failed | Cloudflare/Wrangler deployment error |

---

### Get Deployment Domain by Repo ID

**Endpoint:** `GET /api/deploy/{repo_id}/domain`

Retrieve the Cloudflare Pages domain for a deployed repository using its `repo_id`.

#### Request

```bash
curl "http://localhost:5000/api/deploy/1126661988/domain"
```

#### Response (Success)

```json
{
  "success": true,
  "repo_id": "1126661988",
  "project_name": "tesf",
  "domain": "https://tesf.pages.dev",
  "username": "MDavidka",
  "git_url": "https://github.com/MDavidka/tesf",
  "owner": "MDavidka",
  "repo_name": "tesf"
}
```

#### Response (Error)

```json
{
  "success": false,
  "message": "Invalid repo_id format. Expected numeric identifier."
}
```

#### Error Codes

| HTTP Status | Message | Cause |
|-------------|---------|-------|
| 400 | Invalid repo_id format. Expected numeric identifier. | `repo_id` is not numeric |
| 404 | Repository {repo_id} not found | repo_id not present in git_connection |
| 404 | Repository name not found for repository | Missing `repo_name` and unparsable `git_url` |
| 500 | Failed to retrieve deployment domain | Unexpected server error |

---

### List All Repositories

**Endpoint:** `GET /api/repos`

Fetches all repositories from all users in the database.

#### Request

```bash
curl "http://localhost:5000/api/repos"
```

#### What the API Provides

- Retrieves all user documents with `git_connection` dictionaries
- Parses each `git_url` to extract owner and repository name
- Returns a flattened list of all repositories

#### Response Format

```json
{
  "success": true,
  "repositories": [
    {
      "username": "MDavidka",
      "repo_id": "1126661988",
      "git_url": "https://github.com/MDavidka/tesf",
      "name": "tesf",
      "owner": "MDavidka",
      "full_name": "MDavidka/tesf"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `username` | string | User who owns this repository entry |
| `repo_id` | string | Repository identifier |
| `git_url` | string | Full GitHub repository URL |
| `name` | string | Repository name (from repo_name field or parsed from git_url) |
| `owner` | string | GitHub owner/organization (parsed from git_url) |
| `full_name` | string | Full repository path (owner/repo) |

---

### List User Repositories

**Endpoint:** `GET /api/repos/{username}`

Fetches all repositories for a specific user.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | Yes | The username to fetch repositories for |

#### Request

```bash
curl "http://localhost:5000/api/repos/MDavidka"
```

#### Response Format

```json
{
  "success": true,
  "username": "MDavidka",
  "repositories": [
    {
      "repo_id": "1126661988",
      "git_url": "https://github.com/MDavidka/tesf",
      "name": "tesf",
      "owner": "MDavidka",
      "full_name": "MDavidka/tesf"
    }
  ]
}
```

---

### Health Check

**Endpoint:** `GET /api/health`

Simple health check to verify the server is running.

#### Request

```bash
curl "http://localhost:5000/api/health"
```

#### Response Format

```json
{
  "status": "healthy",
  "service": "M1 Instance - Sycord Deployment Server",
  "instance": "M1"
}
```

---

### Get Recent Logs

**Endpoint:** `GET /api/logs`

Retrieve recent in-memory server logs. Logs are tagged by project and include timestamp/level prefixes.

#### Query Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `project_id` | string | No | Filters logs by project tag. Defaults to the server `PROJECT_ID` if omitted. |
| `limit` | integer | No | Number of most recent log lines to return (default 200, max 500). |

#### Request

```bash
# Default project, last 200 lines
curl "http://localhost:5000/api/logs"

# Specific project tag with custom limit
curl "http://localhost:5000/api/logs?project_id=6957a3fb538e5f68b68b58f7&limit=50"
```

#### Response Format

```json
{
  "success": true,
  "project_id": "6957a3fb538e5f68b68b58f7",
  "logs": [
    "2026-01-02 10:56:42,117 [INFO] [6957a3fb538e5f68b68b58f7-log] Deployment successful! Project: test",
    "2026-01-02 10:56:43,501 [INFO] [6957a3fb538e5f68b68b58f7-log] Cleaning up temporary directory: /tmp/github_repo_abcd1234"
  ]
}
```

If the `project_id` is not provided, the response uses the server's configured project tag.

---

## Error Handling

All error responses follow this format:

```json
{
  "success": false,
  "message": "Human-readable error message",
  "error": "Detailed technical error (when available)"
}
```

### Common HTTP Status Codes

| Status | Meaning |
|--------|---------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Resource doesn't exist |
| 500 | Server Error - Internal processing error |

---

## Deployment Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                    DEPLOYMENT FLOW                               │
└─────────────────────────────────────────────────────────────────┘

1. REQUEST
   ┌─────────────────┐
   │ Client Request  │ → GET/POST /api/deploy/{repo_id}
   └─────────────────┘

2. VALIDATION
   ┌─────────────────┐
   │ Validate Input  │ → Check repo_id is numeric
   └─────────────────┘

3. DATABASE LOOKUP
   ┌─────────────────┐
   │ MongoDB Query   │ → Find repo in git_connection[repo_id] across users
   └─────────────────┘
         │
         ▼
   ┌─────────────────┐
   │ Retrieved Data  │ → git_url, git_token
   └─────────────────┘

4. GITHUB DOWNLOAD
   ┌─────────────────┐
   │ Parse git_url   │ → Extract owner/repo
   └─────────────────┘
         │
         ▼
   ┌─────────────────┐
   │ Download ZIP    │ → GitHub API with git_token
   └─────────────────┘

5. CLOUDFLARE DEPLOYMENT
   ┌─────────────────┐
   │ Create Project  │ → Cloudflare API (if needed)
   └─────────────────┘
         │
         ▼
   ┌─────────────────┐
   │ Deploy Files    │ → wrangler pages deploy
   └─────────────────┘

6. RESPONSE
   ┌─────────────────┐
   │ Return Result   │ → success, url, project_name
   └─────────────────┘
```

---

## Example Usage

### Complete Deployment Example

```bash
# 1. Check available repositories
curl http://localhost:5000/api/repos

# 2. Deploy a specific repository
curl -X POST http://localhost:5000/api/deploy/1126661988

# 3. Check deployment result
# Response:
# {
#   "success": true,
#   "message": "Deployment successful! Project: tesf",
#   "url": "https://tesf.pages.dev",
#   ...
# }
```

### Using with JavaScript

```javascript
// Fetch repositories
const reposResponse = await fetch('/api/repos');
const { repositories } = await reposResponse.json();

// Deploy a repository
const deployResponse = await fetch(`/api/deploy/${repo_id}`, {
  method: 'POST'
});
const result = await deployResponse.json();

if (result.success) {
  console.log(`Deployed to: ${result.url}`);
}
```

---

## Notes

1. **repo_id Format**: The `repo_id` must be a numeric string. This is validated on every deploy request.

2. **git_connection Structure**: `git_connection` is a dictionary where keys are `repo_id` values and values are the repository documents.

3. **git_url Format**: The API supports GitHub URLs in these formats:
   - `https://github.com/owner/repo`
   - `https://github.com/owner/repo.git`
   - `git@github.com:owner/repo.git`

4. **git_token Permissions**: The GitHub token must have `repo` scope to access private repositories.

5. **Cloudflare Project Names**: Repository names are sanitized for Cloudflare (lowercase, alphanumeric and hyphens only, max 63 characters).
