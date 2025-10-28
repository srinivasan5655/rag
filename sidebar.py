with st.sidebar:
    st.header("🔧 Configuration")
    
    # Index settings
    index_dir = os.getenv("INDEX_DIR", ".rag_index")
    os.makedirs(index_dir, exist_ok=True)
    index_path = os.path.join(index_dir, "index.faiss")
    
    # Analysis settings
    st.subheader("Analysis Settings")
    max_chunk = st.number_input("Max chunk size (chars)", value=1800, min_value=500, max_value=3000)
    overlap = st.number_input("Chunk overlap", value=200, min_value=50, max_value=500)
    
    # Cosmos Gremlin status
    gremlin_enabled = all([
        os.getenv("COSMOS_GREMLIN_ENDPOINT"),
        os.getenv("COSMOS_GREMLIN_PRIMARY_KEY"),
        os.getenv("COSMOS_GREMLIN_DATABASE"),
        os.getenv("COSMOS_GREMLIN_GRAPH"),
    ])
    #st.write(f"Graph DB: {'✅ Enabled' if gremlin_enabled else '❌ Disabled'}")
    
    # Action buttons
    st.subheader("Actions")
    
    col1, col2, col3 = st.columns(3)
    with col1:
        rebuild_index = st.button("🔄 Build/Append Index", type="primary")
    with col2:
        clear_index = st.button("🗑️ Clear Index")
    with col3:
        clear_data = st.button("🗑️ Clear Session")
    
    # Append mode checkbox
    append_mode = st.checkbox("📎 Append Mode (add to existing index)", value=True, 
                              help="When enabled, new uploads will be added to existing index instead of replacing it")
    
    if clear_index:
        index_path = os.path.join(st.session_state.get('index_dir', '.rag_index'), "index.faiss")
        meta_path = index_path.replace(".faiss", ".meta.pkl")
        if os.path.exists(index_path):
            os.remove(index_path)
            if os.path.exists(meta_path):
                os.remove(meta_path)
            st.success("✅ Index cleared!")
            st.rerun()
        else:
            st.info("No index to clear")
    
    if clear_data:
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("✅ Session data cleared!")
        st.rerun()
    
    if rebuild_index:
        if not workdir or not os.path.exists(workdir):
            st.warning("Please upload files first!")
        else:
            with st.spinner("🔄 Building/Updating FAISS index..."):
                try:
                    from utils import sliding_window, read_text_safe
                    
                    # Collect all code files
                    code_docs = []
                    for root, _, files in os.walk(workdir):
                        for file in files:
                            full_path = os.path.join(root, file)
                            if any(full_path.endswith(ext) for ext in CODE_EXTS):
                                text = read_text_safe(full_path)
                                if text.strip():
                                    chunks = sliding_window(text, max_chunk, overlap)
                                    for idx, chunk in enumerate(chunks):
                                        code_docs.append({
                                            "text": chunk,
                                            "path": os.path.relpath(full_path, workdir),
                                            "chunk_id": idx,
                                            "type": "code"
                                        })
                    
                    st.info(f"📊 Prepared {len(code_docs)} code chunks")
                    
                    # Get support documents separately
                    support_docs = st.session_state.get("support_docs", [])
                    if support_docs:
                        st.info(f"📎 Including {len(support_docs)} supporting document chunks")
                    
                    # Check append mode
                    # if append_mode and os.path.exists(index_path):
                    #     st.info("📎 Append mode: Adding to existing index...")
                    #     # Combine for append operation
                    #     all_docs = code_docs + support_docs
                    #     add_documents_to_index(index_path, all_docs, use_checkpoint=True)
                        
                    #     # Reload index to update session state
                    #     idx, texts, meta, _, _ = load_index(index_path)
                    #     st.session_state.index = idx
                    #     st.session_state.texts = texts
                    #     st.session_state.metadata = meta
                        
                    #     st.success(f"✅ Added {len(all_docs)} items! Index: {idx.ntotal} vectors")
                    # else:
                    #     st.info("🔨 Building new index from scratch...")
                    #     # Pass code and support docs separately
                    #     idx, meta = build_faiss_index(code_docs, index_path, use_checkpoint=True, supporting_docs=parsed.get("supporting_docs", []))
                    #     # , resume_from_checkpoint=True
                    #     if idx:
                    #         st.session_state.index = idx
                    #         st.session_state.texts = [m.get("text", "") for m in meta]
                    #         st.session_state.metadata = meta
                    #         st.success(f"✅ Index created: {idx.ntotal} vectors")
                    
                    # DON'T clear support docs after indexing - keep them for Q&A tab
                    if "support_docs" in st.session_state:
                        del st.session_state["support_docs"]
                        
                except Exception as e:
                    st.error(f"Index building failed: {str(e)}")
                    st.exception(e)

