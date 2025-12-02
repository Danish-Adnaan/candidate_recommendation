# MongoDB Atlas Vector Search Setup Guide

## Overview

This guide explains how to set up the MongoDB Atlas Vector Search index required for the semantic candidate recommendation system.

## Prerequisites

- MongoDB Atlas account with a cluster
- Database: `dev`
- Collection: `userprofiles` (should already exist with candidate data)
- Candidate documents should have `embedding_vector` field with 3072-dimensional vectors

## Why is this needed?

The semantic search feature uses MongoDB Atlas's Vector Search capability to find candidates similar to job descriptions. This requires a special **Atlas Vector Search index** (different from regular MongoDB indexes) that enables efficient similarity searches using cosine similarity.

**Important**: Vector Search indexes can only be created through the Atlas UI or Atlas CLI, not programmatically via the MongoDB driver.

---

## Step-by-Step Index Creation

### 1. Access MongoDB Atlas

1. Go to [https://cloud.mongodb.com/](https://cloud.mongodb.com/)
2. Log in to your account
3. Select your project and cluster

### 2. Navigate to Search Indexes

1. Click **"Database"** in the left sidebar
2. Click **"Browse Collections"**
3. Find and select your database: **`dev`**
4. Find and select your collection: **`userprofiles`**
5. Click the **"Search Indexes"** tab (NOT the regular "Indexes" tab)

### 3. Create the Vector Search Index

1. Click the **"Create Search Index"** button
2. Select **"Atlas Vector Search"** (not "Atlas Search")
3. Choose **"JSON Editor"** configuration method
4. Enter the following details:

   **Index Name**: `userprofiles_embedding_index`

   **Index Definition** (paste this JSON):
   ```json
   {
     "fields": [
       {
         "type": "vector",
         "path": "embedding_vector",
         "numDimensions": 3072,
         "similarity": "cosine"
       }
     ]
   }
   ```

5. Click **"Create Search Index"**

### 4. Wait for Index to Build

- The index status will initially show as "Building" or "Pending"
- Wait 2-5 minutes for the status to change to **"Active"**
- You can refresh the page to check the status
- The build time depends on the number of documents (775 documents should build quickly)

### 5. Verify Index is Active

Once the index shows **"Active"** status, you're ready to use the search endpoints!

---

## Verifying the Setup

### Option 1: Run the diagnostic script

```bash
python check_vector_index.py
```

**Expected output**:
```
✓ Found 1 vector-related index(es)
Index: userprofiles_embedding_index
```

### Option 2: Test the API endpoints

1. Start the FastAPI server:
   ```bash
   uvicorn app.main:app --reload
   ```

2. Test the applied search endpoint:
   ```
   http://localhost:8000/search/applied?job_id=68fb8c679978f548ce73563a&page=1&count=50
   ```

3. Test the global search endpoint:
   ```
   http://localhost:8000/search/global?job_id=68fb8c679978f548ce73563a&count=50
   ```

**Expected**: Both endpoints should return 200 OK with JSON containing candidate results ranked by similarity score.

---

## Troubleshooting

### Error: "$vectorSearch is only valid..."

**Cause**: The vector search index hasn't been created yet or isn't active.

**Solution**: 
1. Check that you created the index in the **"Search Indexes"** tab (not regular "Indexes")
2. Verify the index status is **"Active"** (not "Building" or "Pending")
3. Wait a few more minutes if the index is still building
4. Restart your FastAPI server after the index becomes active

### Index not appearing in the list

**Cause**: You may have created a regular index instead of a Search index.

**Solution**:
1. Make sure you're in the **"Search Indexes"** tab
2. Delete any incorrectly created indexes
3. Follow the steps above to create an **Atlas Vector Search** index (not a regular index)

### Wrong number of dimensions error

**Cause**: The index was created with incorrect `numDimensions` value.

**Solution**:
1. Delete the existing vector search index
2. Create a new one with `numDimensions: 3072` (must match the embedding model)

### No results returned from search

**Possible causes**:
1. No candidates have embeddings yet
   - Run: `python check_vector_index.py` to verify
   - Should show "Documents with embedding_vector: 775"
   
2. Job embedding generation failed
   - Check server logs for errors
   - Verify Azure OpenAI credentials in `.env` file

3. No applications for the job ID
   - For `/search/applied`, there must be applications with `currentStatus="Applied"`
   - Try `/search/global` instead, which searches all candidates

---

## Index Configuration Details

### Field Explanations

- **type**: `"vector"` - Specifies this is a vector search field
- **path**: `"embedding_vector"` - The field name in documents containing the vector
- **numDimensions**: `3072` - Must match the Azure OpenAI `text-embedding-3-large` model output
- **similarity**: `"cosine"` - The similarity metric used for ranking (cosine similarity)

### Why Cosine Similarity?

Cosine similarity measures the angle between vectors, making it ideal for semantic similarity:
- Range: -1 to 1 (higher is more similar)
- Normalizes for vector magnitude
- Industry standard for text embeddings
- Works well with Azure OpenAI embeddings

---

## Additional Resources

- [MongoDB Atlas Vector Search Documentation](https://www.mongodb.com/docs/atlas/atlas-vector-search/vector-search-overview/)
- [Atlas Vector Search Tutorial](https://www.mongodb.com/docs/atlas/atlas-vector-search/tutorials/)
- [Azure OpenAI Embeddings](https://learn.microsoft.com/en-us/azure/ai-services/openai/concepts/understand-embeddings)

---

## Need Help?

If you encounter issues not covered in this guide:
1. Check the MongoDB Atlas documentation
2. Verify your Azure OpenAI credentials
3. Check the FastAPI server logs for detailed error messages
4. Run `python check_vector_index.py` for diagnostic information
