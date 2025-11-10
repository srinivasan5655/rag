import graphviz

with tab7:
    st.markdown("""
    <style>
        .diagram-header {
            text-align: center;
            padding: 0.8rem;
            background: linear-gradient(90deg, #3b82f6, #9333ea);
            color: white;
            border-radius: 10px;
            font-size: 1.4rem;
            font-weight: 600;
            margin-bottom: 1.2rem;
        }
        .diagram-box {
            background-color: #f9fafc;
            border: 1px solid #e5e7eb;
            border-radius: 12px;
            padding: 1.5rem;
            box-shadow: 0 4px 8px rgba(0,0,0,0.05);
        }
        .diagram-footer {
            text-align: center;
            margin-top: 1.5rem;
            font-size: 0.9rem;
            color: #6b7280;
        }
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="diagram-header">✨ Azure AI Diagram Generator</div>', unsafe_allow_html=True)

    st.markdown("""
    <div style="text-align:center; color:#4b5563; font-size:1.05rem;">
        Generate professional architecture visuals powered by Azure OpenAI and Mermaid.
    </div>
    """, unsafe_allow_html=True)

    # Choose diagram type (Dropdown instead of Radio)
    diagram_type = st.selectbox(
        "🧩 Choose diagram type:",
        [
            "ER Diagram",
            "Flowchart",
            "Sequence Diagram",
            "Class Diagram",
            "Architecture Diagram",
            "Component Diagram",
            "Deployment Diagram"
        ],
        index=0
    )

    # Diagram generation section
    st.markdown('<div class="diagram-box">', unsafe_allow_html=True)
    generate_button = st.button("🎨 Generate Diagram Image", use_container_width=True)
    st.markdown('</div>', unsafe_allow_html=True)

    def generate_mermaid(diagram_type):
        idx, texts, meta ,tokenized, vecs = load_index(index_path)
        seed_results = query(idx, texts, meta, "overview main modules data access business processes controllers", top_k=15)
        raw = generate_dot(            
            seed_results,
            diagram_type,
            parsed["nodes"],
            parsed.get("metrics"),
            parsed.get("business_processes"),
            power_mapping)
        print("Generated Mermaid Content:\n", raw)
        match = re.search(r"```mermaid\n(.*?)```", raw, re.DOTALL)
        return match.group(1).strip() if match else raw.strip()

    
    def extract_dot(text: str) -> str:
        if not text or not text.strip():
            raise ValueError("Empty response")

        fenced = re.search(r"```(?:dot)?\s*(.*?)```", text, re.S | re.I)
        if fenced:
            return fenced.group(1).strip()

        start = re.search(r"(digraph|graph)\b", text, re.I)
        if start:
            idx = start.start()
            last_brace = text.rfind("}")
            if last_brace != -1:
                return text[idx:last_brace + 1].strip()
            return text[idx:].strip()

        if "->" in text or "--" in text:
            return text.strip()

        raise ValueError("No DOT code found in the LLM response.")



    if generate_button:
        with st.spinner("⚙️ Generating diagram..."):
            try:
                dot = None
                raw = generate_mermaid(diagram_type)
                try:
                    dot = extract_dot(raw)
                except Exception as e:
                    st.error(f"Failed to extract DOT: {e}")
                

                if dot:
                    st.success("DOT extracted.")
                    st.subheader("DOT code")
                    st.code(dot, language="dot")

                    st.subheader("Rendered diagram")
                    try:
                        st.graphviz_chart(dot)
                    except Exception as e:
                        st.error(f"Graphviz render failed: {e}")
                        # fallback using graphviz package
                        try:
                            src = graphviz.Source(dot)
                            tmp = tempfile.NamedTemporaryFile(suffix=".svg", delete=False)
                            out_path = src.render(filename=tmp.name, format="svg", cleanup=True)
                            st.image(out_path)
                        except Exception as e2:
                            st.error(f"Fallback render failed: {e2}")

                    st.download_button("Download DOT", data=dot, file_name="diagram.dot", mime="text/plain")


            except Exception as e:
                st.error(f"Error generating diagram: {str(e)}")







  # brd_generator.py

  def generate_dot(retrieved: List[Dict[str, Any]], 
                    diagram_type: str,
                 nodes: List[Dict[str, Any]], 
                 metrics: Dict[str, Any] = None,
                 business_processes: List[Dict[str, Any]] = None,
                 power_platform_mapping: Dict[str, Any] = None,
                 ) -> str:
    """Generate comprehensive BRD with metrics and Power Platform focus"""
    try:
        graph_summary = summarize_graph_enhanced(nodes)
        context = _make_context_snippets(retrieved, max_chars=15000)
        
        # Format additional context
        metrics_summary = format_metrics_summary(metrics or {})
        processes_summary = format_business_processes(business_processes or [])
        mapping_summary = format_power_platform_mapping(power_platform_mapping or {})
        
        messages = [
            {"role": "system", "content": f'''You are a software architect with the details given below
              Generate valid  Graphviz DOT format code for a {diagram_type.lower()}.
              
              Return only valid DOT code (no additional explanation). Prefer directed graph (digraph).

              "Wrap output in triple-backtick code block with language 'dot' if possible.

              '''},
            {"role": "user", "content": f"""
            GRAPH:
            {graph_summary}

            {metrics_summary}

            {processes_summary}

            {mapping_summary}

            CONTEXT SNIPPETS:
            {context}
            """}
        ]
        content = _chat(messages, temperature=0.1)
        return content
    except Exception as e:
        print(f"⚠️  Error preparing BRD context: {str(e)}")
        return "Error generating BRD."
    # Generate BRD content




    st.markdown('<div class="diagram-footer">Powered by Azure OpenAI + Mermaid CLI ⚡</div>', unsafe_allow_html=True)


