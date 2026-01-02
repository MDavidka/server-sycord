# Sycord Deployment Server - API Documentation

This document provides detailed information about the deployment API endpoints, including request/response formats, expected parameters, and what the API provides.

## Table of Contents

1. [Database Structure](#database-structure)
2. [API Endpoints](#api-endpoints)
   - [Deploy by Username and Repo ID](#deploy-by-username-and-repo-id)
   - [List All Repositories](#list-all-repositories)
   - [List User Repositories](#list-user-repositories)
   - [Health Check](#health-check)
3. [Error Handling](#error-handling)
4. [Deployment Flow](#deployment-flow)

---

## Database Structure

The API expects repositories to be stored in MongoDB with the following structure:

**Database:** `main`  
**Collection:** `users`  
**Path:** `main > users > {username} > git_connection > [{repo documents}]`

### User Document Schema

```json
{
  "_id": ObjectId("..."),
  "username": "user1",
  "git_connection": [
    {
      "username": "user1",
      "repo_id": "12345",
      "git_url": "https://github.com/owner/repository-name",
      "git_token": "ghp_xxxxxxxxxxxxxxxxxxxx"
    }
  ]
}
```

### Field Descriptions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `username` | string | Yes | The username of the repository owner in the system |
| `repo_id` | string | Yes | A unique **5-digit** identifier for the repository (e.g., "12345", "00001", "99999") |
| `git_url` | string | Yes | The GitHub repository URL in HTTPS format (e.g., `https://github.com/owner/repo`) |
| `git_token` | string | Yes | GitHub personal access token with `repo` scope for accessing the repository |

---

## API Endpoints

### Deploy by Username and Repo ID

**Endpoint:** `GET/POST /api/deploy/{username}/{repo_id}`

This is the primary deployment endpoint that triggers a deployment from a GitHub repository to Cloudflare Pages.

#### URL Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `username` | string | Yes | The username of the repository owner |
| `repo_id` | string | Yes | **5-digit** repository identifier |

#### What the API Expects

1. **Valid `username`** - Must exist in the `users` collection
2. **Valid `repo_id`** - Must be exactly 5 digits (00000-99999)
3. **Repository document** - Must contain `git_url` and `git_token`

#### Request Examples

```bash
# Using GET request
curl "http://localhost:5000/api/deploy/user1/12345"

# Using POST request
curl -X POST "http://localhost:5000/api/deploy/user1/12345"

# Using POST with headers (no body required)
curl -X POST "http://localhost:5000/api/deploy/user1/12345" \
  -H "Accept: application/json"
```

#### What the API Provides

The API performs the following actions:

1. **Validation**
   - Validates that `repo_id` is exactly 5 digits
   - Checks that the user exists in the database
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
  "message": "Deployment successful! Project: my-repo",
  "project_name": "my-repo",
  "url": "https://my-repo.pages.dev",
  "username": "user1",
  "repo_id": "12345",
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
| 400 | Invalid repo_id format. Expected 5-digit identifier. | `repo_id` is not exactly 5 digits |
| 404 | Repository {repo_id} not found for user {username} | User or repository doesn't exist |
| 404 | GitHub token (git_token) not found for repository | Missing `git_token` in database |
| 404 | Git URL (git_url) not found for repository | Missing `git_url` in database |
| 400 | Could not parse git_url: {url} | Invalid GitHub URL format |
| 500 | Failed to download repository from GitHub | GitHub API error or invalid token |
| 500 | Deployment failed | Cloudflare/Wrangler deployment error |

---

### List All Repositories

**Endpoint:** `GET /api/repos`

Fetches all repositories from all users in the database.

#### Request

```bash
curl "http://localhost:5000/api/repos"
```

#### What the API Provides

- Retrieves all user documents with `git_connection` arrays
- Parses each `git_url` to extract owner and repository name
- Returns a flattened list of all repositories

#### Response Format

```json
{
  "success": true,
  "repositories": [
    {
      "username": "user1",
      "repo_id": "12345",
      "git_url": "https://github.com/owner/my-repo",
      "name": "my-repo",
      "owner": "owner",
      "full_name": "owner/my-repo"
    },
    {
      "username": "user2",
      "repo_id": "67890",
      "git_url": "https://github.com/another-owner/another-repo",
      "name": "another-repo",
      "owner": "another-owner",
      "full_name": "another-owner/another-repo"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `username` | string | User who owns this repository entry |
| `repo_id` | string | 5-digit repository identifier |
| `git_url` | string | Full GitHub repository URL |
| `name` | string | Repository name (parsed from git_url) |
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
curl "http://localhost:5000/api/repos/user1"
```

#### Response Format

```json
{
  "success": true,
  "username": "user1",
  "repositories": [
    {
      "repo_id": "12345",
      "git_url": "https://github.com/owner/my-repo",
      "name": "my-repo",
      "owner": "owner",
      "full_name": "owner/my-repo"
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
   │ Client Request  │ → GET/POST /api/deploy/{username}/{repo_id}
   └─────────────────┘

2. VALIDATION
   ┌─────────────────┐
   │ Validate Input  │ → Check repo_id is 5 digits
   └─────────────────┘

3. DATABASE LOOKUP
   ┌─────────────────┐
   │ MongoDB Query   │ → Find user → Find repo in git_connection
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
curl -X POST http://localhost:5000/api/deploy/user1/12345

# 3. Check deployment result
# Response:
# {
#   "success": true,
#   "message": "Deployment successful! Project: my-repo",
#   "url": "https://my-repo.pages.dev",
#   ...
# }
```

### Using with JavaScript

```javascript
// Fetch repositories
const reposResponse = await fetch('/api/repos');
const { repositories } = await reposResponse.json();

// Deploy a repository
const deployResponse = await fetch(`/api/deploy/${username}/${repo_id}`, {
  method: 'POST'
});
const result = await deployResponse.json();

if (result.success) {
  console.log(`Deployed to: ${result.url}`);
}
```

---

## Notes

1. **5-Digit repo_id**: The `repo_id` must be exactly 5 digits (00000-99999). This is validated on every deploy request.

2. **git_url Format**: The API supports GitHub URLs in these formats:
   - `https://github.com/owner/repo`
   - `https://github.com/owner/repo.git`
   - `git@github.com:owner/repo.git`

3. **git_token Permissions**: The GitHub token must have `repo` scope to access private repositories.

4. **Cloudflare Project Names**: Repository names are sanitized for Cloudflare (lowercase, alphanumeric and hyphens only, max 63 characters).
