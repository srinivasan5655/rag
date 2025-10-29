import tiktoken
import logging
# Ensure logs directory exists
LOG_DIR = os.path.join(os.getcwd(), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
LOG_FILE = os.path.join(LOG_DIR, "run_prompt_array.log")

# Global memory
conversation_history = []

# =========================
# ✅ Utility: Token Counter
# =========================
def count_tokens(text: str, encoding_name: str = "cl100k_base") -> int:
    enc = tiktoken.get_encoding(encoding_name)
    return len(enc.encode(text))

# =========================
# ✅ Utility: Message Trimmer
# =========================
def trim_messages(messages: List[Dict[str, str]], max_tokens: int = 60000) -> List[Dict[str, str]]:
    """
    Keep only the most recent messages that fit within the max token limit.
    """
    enc = tiktoken.get_encoding("cl100k_base")
    total_tokens = 0
    trimmed = []

    # Traverse backwards (newest first)
    for msg in reversed(messages):
        msg_tokens = len(enc.encode(msg["content"]))
        if total_tokens + msg_tokens > max_tokens:
            break
        trimmed.insert(0, msg)
        total_tokens += msg_tokens

    return trimmed

# =========================
# ✅ Utility: Summarize Older Messages
# =========================
def summarize_old_conversation(messages: List[Dict[str, str]], _chat_func, temperature=0.1) -> str:
    """
    Summarize earlier conversation history to save tokens.
    """
    summary_prompt = "Summarize the above conversation into 5 concise bullet points preserving key details."
    try:
        summary = _chat_func(messages + [{"role": "user", "content": summary_prompt}], temperature=temperature)
        return summary.strip()
    except Exception:
        return "Summary unavailable (fallback)."

# =========================
# ✅ Main Function
# =========================
def run_prompt_array(prompt_list: List[str],
                     retrieved: List[Dict[str, Any]], 
                     nodes: List[Dict[str, Any]], 
                     metrics: Dict[str, Any] = None,
                     business_processes: List[Dict[str, Any]] = None,
                     power_platform_mapping: Dict[str, Any] = None, 
                     system_prompt: str = "", 
                     temperature: float = 0.1,
                     max_retries: int = 5,
                     max_context_tokens: int = 60000) -> str:
    """
    Execute multiple prompts conversationally with:
    - Context persistence
    - Token trimming
    - Summarization
    - Retry + Progress bar + ETA
    """

    if not prompt_list:
        return "⚠️ No prompts provided."

    # Setup logging
    logging.basicConfig(filename="logs/run_prompt_array.log", level=logging.INFO, format="%(asctime)s - %(message)s")

    print(f"\n🚀 Running {len(prompt_list)} conversational prompts...\n")
    results = []

    # Prepare shared context once
    graph_summary = summarize_graph_enhanced(nodes)
    context = _make_context_snippets(retrieved, max_chars=15000)
    metrics_summary = format_metrics_summary(metrics or {})
    processes_summary = format_business_processes(business_processes or [])
    mapping_summary = format_power_platform_mapping(power_platform_mapping or {})

    # Initialize conversation history
    messages = [
        {
            "role": "system",
            "content": f"""{system_prompt}

            This is a multi-turn conversation. Each response builds upon previous exchanges.

            GRAPH:
            {graph_summary}

            {metrics_summary}

            {processes_summary}

            {mapping_summary}

            CONTEXT SNIPPETS:
            {context}
            """
                    }
                ]

    # Progress bar
    pbar = tqdm(total=len(prompt_list), desc="Conversational flow", unit="prompt")

    for i, prompt in enumerate(prompt_list, start=1):
        start_time = time.time()
        messages.append({"role": "user", "content":base +  prompt})

        # 💡 Token Management
        total_tokens = sum(count_tokens(m["content"]) for m in messages)
        if total_tokens > max_context_tokens * 0.9:  # if nearing token limit
            logging.info(f"🧹 Summarizing old messages (token count: {total_tokens})")
            summary = summarize_old_conversation(messages[:10], _chat)
            messages = messages[10:]  # remove oldest
            messages.insert(1, {"role": "assistant", "content": f"Conversation so far:\n{summary}"})

        # Trim to ensure safety
        messages = trim_messages(messages, max_tokens=max_context_tokens)

        retries = 0
        success = False

        while retries < max_retries:
            try:
                response = _chat(messages, temperature=temperature)
                response = response.strip()
                messages.append({"role": "assistant", "content": response})
                results.append(response)

                elapsed = time.time() - start_time
                pbar.set_postfix_str(f"✅ Prompt {i} done ({elapsed:.1f}s)")
                logging.info(f"Prompt {i} succeeded ({elapsed:.1f}s)")
                success = True
                break

            except Exception as e:
                error_text = str(e).lower()
                logging.error(f"Prompt {i} error: {e}")

                if "rate limit" in error_text or "429" in error_text:
                    wait_time = 60 + random.uniform(5, 15)
                    pbar.set_postfix_str(f"⏳ Rate limit hit, waiting {wait_time:.1f}s")
                    time.sleep(wait_time)
                    retries += 1
                elif "timeout" in error_text or "connection" in error_text:
                    wait_time = (2 ** retries) * 5
                    pbar.set_postfix_str(f"⚠️ Timeout, retrying in {wait_time}s")
                    time.sleep(wait_time)
                    retries += 1
                else:
                    results.append(f"[Error in prompt {i}: {e}]")
                    pbar.set_postfix_str(f"❌ Error: {str(e)[:40]}...")
                    break

        if not success and retries >= max_retries:
            results.append(f"[Failed after {max_retries} retries]")
            pbar.set_postfix_str("❌ Max retries exceeded")
            logging.warning(f"Prompt {i} failed after {max_retries} retries")

        pbar.update(1)
        time.sleep(0.3)

    pbar.close()

    print("\n🧩 Merging all responses into one conversational transcript...")
    transcript = "\n\n".join(
        [f"User {i}: {prompt}\nAssistant: {res}" for i, (prompt, res) in enumerate(zip(prompt_list, results), 1)]
    )

    return transcript



def build_faiss_index(
    chunks: List[Dict[str, Any]],
    index_path: str,
    use_checkpoint: bool = True,
    supporting_docs: Optional[List[Dict[str, Any]]] = None
) -> Tuple[faiss.Index, List[Dict[str, Any]]]:
    """
    Build FAISS index from chunks and optional supporting documents.
    """
    print(f"\n{'='*60}")
    print("🏗️  BUILDING FAISS INDEX (WITH SUPPORT DOCS)" if supporting_docs else "🏗️  BUILDING FAISS INDEX")
    print(f"{'='*60}")
    
    start_time = time.time()
    
    # Prepare texts and metadata
    texts = []
    metadata = []
    
    print(f"📦 Processing {len(chunks)} code chunks...")
    
    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        if not chunk_text or not chunk_text.strip():
            continue
        
        texts.append(chunk_text)
        metadata.append({
            "text": chunk_text,
            "type": "code_chunk",
            "path": chunk.get("path", ""),
            "kind": chunk.get("kind", "code_chunk"),
            "hash": chunk.get("hash", ""),
            "metrics": chunk.get("metrics", {})
        })
    
    # Optional: Include supporting docs
    if supporting_docs:
        print(f"📚 Including {len(supporting_docs)} supporting documents...")
        for doc in supporting_docs:
            text = doc.get("text", "")
            print(f"text length: {len(text)}")
            print(f"source: {doc.get('source', '')}")
            if not text.strip():
                continue
            # Split large docs into smaller chunks
            for piece in sliding_window(text, 1800, 200):
                if not piece.strip():
                    continue
                texts.append(piece)
                metadata.append({
                    "text": piece,
                    "type": "support_doc",
                    "file_name": doc.get("source", ""),
                    "file_path": doc.get("file_path", ""),
                    "ext": doc.get("ext", ""),
                    "hash": doc.get("hash", ""),
                    "kind": "support_doc"
                })
    
    if not texts:
        raise ValueError("No valid chunks or documents to index!")
    
    print(f"✅ {len(texts)} total text segments prepared for embedding")
    
    # Generate embeddings (with checkpoint support)
    checkpoint_path = None
    if use_checkpoint:
        Path(CHECKPOINT_DIR).mkdir(parents=True, exist_ok=True)
        checkpoint_path = os.path.join(CHECKPOINT_DIR, "build_checkpoint.pkl")
    
    try:
        print(f"\n📊 Generating embeddings for {len(texts)} texts...")
        embeddings = _embed_texts_with_retry(texts, checkpoint_path=checkpoint_path)
        
        if len(embeddings) == 0:
            raise ValueError("No embeddings generated!")
        
        if checkpoint_path:
            _clear_checkpoint(checkpoint_path)
            
    except Exception as e:
        print(f"\n❌ Failed to generate embeddings: {e}")
        if checkpoint_path and Path(checkpoint_path).exists():
            print(f"\n💾 Checkpoint saved at: {checkpoint_path}")
            print("💡 Run the index build again to resume from checkpoint.")
        raise
    
    # Create FAISS index
    print(f"\n🔍 Creating FAISS index...")
    dim = embeddings.shape[1]
    index = faiss.IndexFlatL2(dim)
    index.add(embeddings.astype('float32'))
    
    # Save index + metadata
    print(f"💾 Saving index to {index_path}...")
    Path(index_path).parent.mkdir(parents=True, exist_ok=True)
    faiss.write_index(index, index_path)
    
    meta_path = index_path.replace(".faiss", ".meta.pkl")
    print(f"💾 Saving metadata to {meta_path}...")
    with open(meta_path, "wb") as f:
        pickle.dump(metadata, f)
    
    total_time = time.time() - start_time
    print(f"\n{'='*60}")
    print(f"✅ INDEX BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"   📊 Total vectors: {index.ntotal}")
    print(f"   📐 Vector dimension: {dim}")
    print(f"   📝 Metadata entries: {len(metadata)}")
    print(f"   🕒 Total time: {total_time:.2f} seconds")
    print(f"{'='*60}\n")

    print(f"🔎 Verifying FAISS index and metadata alignment...")

    if index.ntotal != len(metadata):
        print(f"⚠️  Mismatch detected! FAISS vectors: {index.ntotal}, Metadata entries: {len(metadata)}")
    else:
        print(f"✅ FAISS vectors ({index.ntotal}) perfectly match metadata entries.")

    # Confirm metadata file exists and is readable
    if not Path(meta_path).exists():
        print(f"❌ Metadata file not found at {meta_path}")
    else:
        try:
            with open(meta_path, "rb") as f:
                loaded_meta = pickle.load(f)
            if len(loaded_meta) == len(metadata):
                print(f"✅ Metadata file successfully verified ({len(loaded_meta)} entries)")
            else:
                print(f"⚠️ Metadata file entry count mismatch ({len(loaded_meta)} vs {len(metadata)})")
        except Exception as e:
            print(f"❌ Failed to read metadata file: {e}")
        
        return index, metadata


