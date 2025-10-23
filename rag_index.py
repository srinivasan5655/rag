# rag_index.py - COMPLETE FILE WITH TOKEN-AWARE EMBEDDING
import os
import pickle
from pathlib import Path
from typing import List, Dict, Any, Tuple
import numpy as np
import faiss
from openai import AzureOpenAI
from rank_bm25 import BM25Okapi
import re
# ============================================================
# Configuration
# ============================================================
EMB_DEPLOY = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "text-embedding-ada-002")
API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "2023-05-15")


# ============================================================
# Token Estimation (same as utils.py)
# ============================================================
def estimate_tokens(text: str) -> int:
    """
    Estimate token count (roughly 1 token per 4 characters for English text)
    This is a fast approximation - actual tokenization would be slower
    """
    words = len(text.split())
    chars = len(text)
    # Average: 1 token ≈ 0.75 words or 4 characters (whichever is higher)
    return max(int(words * 1.3), int(chars / 4))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """
    Truncate text to approximately max_tokens.
    Uses character-based estimation: ~4 chars per token
    """
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    
    # Truncate and add indicator
    truncated = text[:max_chars]
    # Try to break at a newline or space for cleaner truncation
    last_newline = truncated.rfind('\n')
    if last_newline > max_chars * 0.8:  # If newline is in last 20%
        truncated = truncated[:last_newline]
    
    return truncated + "\n... [truncated]"


# ============================================================
# Azure OpenAI Client
# ============================================================
def _get_client() -> AzureOpenAI:
    """Initialize Azure OpenAI client"""
    return AzureOpenAI(
        api_key=os.getenv("AZURE_OPENAI_API_KEY"),
        api_version=API_VERSION,
        azure_endpoint=os.getenv("AZURE_OPENAI_ENDPOINT")
    )


# ============================================================
# TOKEN-AWARE EMBEDDING FUNCTION
# ============================================================
def _embed_texts(texts: List[str]) -> np.ndarray:
    """
    Embed texts in batches with token-aware processing.
    
    Key constraints:
    - Embedding models (text-embedding-ada-002) have 8191 token limit per request
    - We batch multiple texts together, but total tokens must stay under limit
    - Individual texts that exceed limit are truncated
    
    Strategy:
    - Process texts in batches
    - Track cumulative tokens per batch
    - Keep batch under 6000 tokens (safe margin)
    - Truncate individual texts if needed
    """
    client = _get_client()
    all_vecs = []
    
    if not texts:
        return np.array([])
    
    # Token-aware batching
    MAX_TOKENS_PER_BATCH = 4000  # Reduced from 6000 - safer limit
    MAX_TOKENS_PER_TEXT = 4500   # Reduced from 7000 - max tokens for a single text
    
    current_batch = []
    current_tokens = 0
    
    print(f"📊 Embedding {len(texts)} text chunks...")
    
    for idx, text in enumerate(texts):
        # Estimate tokens for this text
        text_tokens = estimate_tokens(text)
        
        # If single text exceeds limit, truncate it
        if text_tokens > MAX_TOKENS_PER_TEXT:
            print(f"⚠️  Chunk {idx+1}: {text_tokens} tokens → truncating to {MAX_TOKENS_PER_TEXT}")
            text = truncate_to_tokens(text, MAX_TOKENS_PER_TEXT)
            text_tokens = estimate_tokens(text)  # Recalculate after truncation
        
        # Check if adding this text would exceed batch limit
        if current_tokens + text_tokens > MAX_TOKENS_PER_BATCH and current_batch:
            # Process current batch
            print(f"  Processing batch: {len(current_batch)} texts, ~{current_tokens} tokens")
            try:
                resp = client.embeddings.create(model=EMB_DEPLOY, input=current_batch)
                batch_vecs = np.array([r.embedding for r in resp.data])
                all_vecs.append(batch_vecs)
            except Exception as e:
                print(f"❌ Error embedding batch: {e}")
                print(f"   Batch had {len(current_batch)} texts with ~{current_tokens} tokens")
                raise
            
            # Start new batch
            current_batch = [text]
            current_tokens = text_tokens
        else:
            current_batch.append(text)
            current_tokens += text_tokens
    
    # Process final batch
    if current_batch:
        print(f"  Processing final batch: {len(current_batch)} texts, ~{current_tokens} tokens")
        try:
            resp = client.embeddings.create(model=EMB_DEPLOY, input=current_batch)
            batch_vecs = np.array([r.embedding for r in resp.data])
            all_vecs.append(batch_vecs)
        except Exception as e:
            print(f"❌ Error embedding final batch: {e}")
            print(f"   Batch had {len(current_batch)} texts with ~{current_tokens} tokens")
            raise
    
    result = np.vstack(all_vecs) if all_vecs else np.array([])
    print(f"✅ Created {result.shape[0]} embeddings (dim={result.shape[1] if len(result.shape) > 1 else 0})")
    return result


# ============================================================
# FAISS Index Building
# ============================================================
# def build_faiss_index(
#     chunks: List[Dict[str, Any]],
#     index_path: str,
#     supporting_docs: List[Dict[str, Any]] = None
# ) -> Tuple[faiss.Index, List[Dict[str, Any]]]:
#     """
#     Build FAISS index from code chunks and optional supporting documents.
    
#     Args:
#         chunks: List of code chunks with 'text' and metadata
#         index_path: Path to save the index
#         supporting_docs: Optional list of supporting documents
    
#     Returns:
#         Tuple of (faiss_index, metadata_list)
#     """
#     print(f"\n🔨 Building FAISS index from {len(chunks)} chunks...")
    
#     # Prepare texts and metadata
#     texts = []
#     metadata = []
    
#     # Add code chunks
#     for chunk in chunks:
#         texts.append(chunk["text"])
#         metadata.append({
#             "type": "code",
#             "file": chunk.get("file", "unknown"),
#             "hash": chunk.get("hash", ""),
#             "text": chunk["text"]
#         })
    
#     # Add supporting documents if provided
#     if supporting_docs:
#         print(f"📄 Adding {len(supporting_docs)} supporting documents...")
#         for doc in supporting_docs:
#             texts.append(doc["text"])
#             metadata.append({
#                 "type": "document",
#                 "title": doc.get("title", "Unknown Document"),
#                 "source": doc.get("source", ""),
#                 "text": doc["text"]
#             })
    
#     if not texts:
#         print("⚠️  No texts to embed!")
#         return None, []
    
#     # Generate embeddings with token awareness
#     print(f"\n🧮 Generating embeddings for {len(texts)} texts...")
#     try:
#         embeddings = _embed_texts(texts)
#     except Exception as e:
#         print(f"❌ Failed to generate embeddings: {e}")
#         raise
    
#     # Create FAISS index
#     print(f"\n🔍 Creating FAISS index...")
#     dim = embeddings.shape[1]
#     index = faiss.IndexFlatL2(dim)
#     index.add(embeddings.astype('float32'))
    
#     # Save index and metadata
#     print(f"💾 Saving index to {index_path}...")
#     Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    
#     faiss.write_index(index, index_path)
#     try:
#         meta_path = index_path.replace(".faiss", ".meta.pkl")
#         print(f"💾 Saving metadata to {meta_path}...")
#         with open(meta_path, "wb") as f:
#             pickle.dump(metadata, f)
#     except Exception as e:
#         print(f"❌ Failed to save metadata: {e}")
#         # raise
    
#     print(f"✅ Index built successfully!")
#     print(f"   - Vectors: {index.ntotal}")
#     print(f"   - Dimensions: {dim}")
#     print(f"   - Files saved: {index_path}, {meta_path}")
    
#     return index, metadata

import time

def build_faiss_index(
    chunks: List[Dict[str, Any]],
    index_path: str,
    supporting_docs: List[Dict[str, Any]] = None
) -> Tuple[faiss.Index, List[Dict[str, Any]]]:
    """
    Build FAISS index from code chunks and optional supporting documents.
    
    Args:
        chunks: List of code chunks with 'text' and metadata
        index_path: Path to save the index
        supporting_docs: Optional list of supporting documents
    
    Returns:
        Tuple of (faiss_index, metadata_list)
    """
    total_start = time.time()
    print(f"\n🔨 Building FAISS index from {len(chunks)} chunks...")

    # Prepare texts and metadata
    texts = []
    metadata = []

    # Add code chunks
    for chunk in chunks:
        texts.append(chunk["text"])
        metadata.append({
            "type": "code",
            "file": chunk.get("file", "unknown"),
            "hash": chunk.get("hash", ""),
            "text": chunk["text"]
        })

    # Add supporting documents if provided
    if supporting_docs:
        print(f"📄 Adding {len(supporting_docs)} supporting documents...")
        for doc in supporting_docs:
            texts.append(doc["text"])
            metadata.append({
                "type": "document",
                "title": doc.get("title", "Unknown Document"),
                "source": doc.get("source", ""),
                "text": doc["text"]
            })

    if not texts:
        print("⚠️  No texts to embed!")
        return None, []

    # Generate embeddings with token awareness
    print(f"\n🧮 Generating embeddings for {len(texts)} texts...")
    embed_start = time.time()
    try:
        embeddings = _embed_texts(texts)
    except Exception as e:
        print(f"❌ Failed to generate embeddings: {e}")
        raise
    embed_time = time.time() - embed_start
    print(f"⏱️ Embedding generation took {embed_time:.2f} seconds")

    # Create FAISS index
    print(f"\n🔍 Creating FAISS index...")
    build_start = time.time()
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings.astype('float32'))
    build_time = time.time() - build_start
    print(f"⏱️ FAISS index creation took {build_time:.2f} seconds")

    # Save index and metadata
    print(f"💾 Saving index to {index_path}...")
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)

    faiss.write_index(index, index_path)
    try:
        meta_path = index_path.replace(".faiss", ".meta.pkl")
        print(f"💾 Saving metadata to {meta_path}...")
        with open(meta_path, "wb") as f:
            pickle.dump(metadata, f)
    except Exception as e:
        print(f"❌ Failed to save metadata: {e}")
        # raise

    total_time = time.time() - total_start
    print(f"✅ Index built successfully!")
    print(f"   - Vectors: {index.ntotal}")
    print(f"   - Dimensions: {dim}")
    print(f"   - Files saved: {index_path}, {meta_path}")
    print(f"   - 🕒 Total build time: {total_time:.2f} seconds")

    return index, metadata

# ============================================================
# FAISS Index Loading
# ============================================================
def load_faiss_index(index_path: str):
    if not Path(index_path).exists():
        raise FileNotFoundError(f"Index not found: {index_path}")
    
    print(f"📂 Loading FAISS index from {index_path}...")
    index = faiss.read_index(index_path)
    
    meta_path = index_path.replace(".faiss", ".meta.pkl")
    if not Path(meta_path).exists():
        raise FileNotFoundError(f"Metadata not found: {meta_path}")
    
    with open(meta_path, "rb") as f:
        metadata = pickle.load(f)
        print(f"📂 Loaded metadata from {meta_path} with {len(metadata)} entries")
    
    texts = [m.get("text", "") for m in metadata]
    tokenized = None
    vectors = None
    
    print(f"✅ Loaded index with {index.ntotal} vectors")
    return index, texts, metadata, tokenized, vectors
# ============================================================
# SEMANTIC SEARCH
# ============================================================
# def semantic_search(
#     index: faiss.Index,
#     texts: List[str],
#     metadata: List[Dict[str, Any]],
#     query_text: str,
#     top_k: int = 5
# ) -> List[Dict[str, Any]]:
#     """
#     Perform semantic search on FAISS index.
    
#     Args:
#         index: FAISS index
#         texts: List of text chunks (for backward compatibility)
#         metadata: List of metadata for each vector
#         query_text: Search query text
#         top_k: Number of results to return (uses top_k for consistency)
    
#     Returns:
#         List of search results with metadata and scores
#     """
#     client = _get_client()
    
#     # Check query token count
#     query_tokens = estimate_tokens(query_text)
#     if query_tokens > 7000:
#         print(f"⚠️  Query has {query_tokens} tokens, truncating to 7000")
#         query_text = truncate_to_tokens(query_text, 7000)
    
#     # Embed query
#     print(f"🔍 Searching for: {query_text[:100]}...")
#     resp = client.embeddings.create(model=EMB_DEPLOY, input=[query_text])
#     query_vec = np.array([resp.data[0].embedding], dtype='float32')
    
#     # Search (use top_k parameter)
#     k = top_k
#     distances, indices = index.search(query_vec, k)
    
#     # Prepare results
#     results = []
#     for i, (dist, idx) in enumerate(zip(distances[0], indices[0])):
#         if idx < len(metadata):
#             result = metadata[idx].copy()
#             result["score"] = float(dist)
#             result["rank"] = i + 1
#             results.append(result)
    
#     print(f"✅ Found {len(results)} results")
#     return results


def _tokenize(text: str) -> list:
    """Tokenizer for BM25 (used inside semantic_search)"""
    return re.findall(r"\w+", text.lower())

def semantic_search(
    index: faiss.Index,
    texts: List[str],
    metadata: List[Dict[str, Any]],
    query_text: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Perform semantic search on FAISS index with BM25 hybrid enhancement.

    Args:
        index: FAISS index
        texts: List of text chunks (for backward compatibility)
        metadata: List of metadata for each vector
        query_text: Search query text
        top_k: Number of results to return

    Returns:
        List of search results with metadata, scores, and hybrid ranking
    """
    client = _get_client()

    # --- Truncate query if too long ---
    query_tokens_count = estimate_tokens(query_text)
    if query_tokens_count > 7000:
        print(f"⚠️ Query has {query_tokens_count} tokens, truncating to 7000")
        query_text = truncate_to_tokens(query_text, 7000)

    # --- FAISS Semantic Search ---
    resp = client.embeddings.create(model=EMB_DEPLOY, input=[query_text])
    query_vec = np.array([resp.data[0].embedding], dtype='float32')
    distances, indices = index.search(query_vec, top_k*2)  # get more for hybrid ranking

    sem_results = {}
    for rank, (dist, idx) in enumerate(zip(distances[0], indices[0])):
        if idx < len(metadata):
            sem_results[idx] = 1 / (dist + 1e-6)  # convert distance to score

    # --- BM25 Search ---
    documents = [_tokenize(m["text"]) for m in metadata]
    bm25 = BM25Okapi(documents)
    query_tokens = _tokenize(query_text)
    bm_scores = bm25.get_scores(query_tokens)
    for idx, score in enumerate(bm_scores):
        if idx in sem_results:
            sem_results[idx] += score  # combine semantic + BM25
        else:
            sem_results[idx] = score

    # --- Sort combined results ---
    sorted_indices = sorted(sem_results, key=lambda i: sem_results[i], reverse=True)[:top_k]
    results = []
    for rank, idx in enumerate(sorted_indices):
        r = metadata[idx].copy()
        r["score"] = float(sem_results[idx])
        r["rank"] = rank + 1
        results.append(r)

    print(f"✅ Hybrid Semantic+BM25 search returned {len(results)} results")
    return results
# ============================================================
# UTILITY: Add Documents to Existing Index
# ============================================================
def add_documents_to_index(
    index_path: str,
    new_docs: List[Dict[str, Any]]
) -> None:
    """
    Add new documents to an existing FAISS index.
    
    Args:
        index_path: Path to existing index
        new_docs: List of new documents to add
    """
    print(f"\n➕ Adding {len(new_docs)} documents to existing index...")
    
    # Load existing index
    index, metadata = load_faiss_index(index_path)
    
    # Prepare new texts
    texts = [doc["text"] for doc in new_docs]
    
    # Generate embeddings
    new_embeddings = _embed_texts(texts)
    
    # Add to index
    index.add(new_embeddings.astype('float32'))
    
    # Update metadata
    for doc in new_docs:
        metadata.append({
            "type": "document",
            "title": doc.get("title", "Unknown"),
            "source": doc.get("source", ""),
            "text": doc["text"]
        })
    
    # Save updated index
    faiss.write_index(index, index_path)
    meta_path = index_path.replace(".index", ".meta.pkl")
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)
    
    print(f"✅ Updated index now has {index.ntotal} vectors")


# ============================================================
# BACKWARD COMPATIBILITY ALIASES
# ============================================================
load_index = load_faiss_index  # Alias for backward compatibility
build_index = build_faiss_index  # Alias for backward compatibility
query = semantic_search  # Alias for backward compatibility


# ============================================================
# MAIN - For Testing
# ============================================================
if __name__ == "__main__":

    from pathlib import Path

    index_dir = os.getenv("INDEX_DIR", ".rag_index")
    index_path = os.path.join(index_dir, "index.faiss")
    with open(index_path, "rb") as f:
        header = f.read(4)
    print("Header bytes:", header)
    # Test token estimation
    test_text = "This is a test " * 1000
    tokens = estimate_tokens(test_text)
    print(f"Test text: {len(test_text)} chars, ~{tokens} tokens")
    
    # Test truncation
    truncated = truncate_to_tokens(test_text, 100)
    print(f"Truncated: {len(truncated)} chars, ~{estimate_tokens(truncated)} tokens")