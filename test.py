def run_prompt_array(prompt_list: List[str],
                     retrieved: List[Dict[str, Any]], 
                 nodes: List[Dict[str, Any]], 
                 metrics: Dict[str, Any] = None,
                 business_processes: List[Dict[str, Any]] = None,
                 power_platform_mapping: Dict[str, Any] = None, 
                 system_prompt: str = "", temperature: float = 0.1) -> str:
    """
    Execute multiple prompts sequentially using the same chat model,
    gather all responses, and combine them into one detailed output.

    Args:
        prompt_list: List of user prompt strings.
        system_prompt: Optional system instruction applied to all.
        temperature: Sampling temperature for creativity control.

    Returns:
        str: Combined, coherent final output.
    """
    if not prompt_list:
        return "⚠️ No prompts provided."

    print(f"\n🚀 Running {len(prompt_list)} prompts sequentially...")
    results = []

    for i, prompt in enumerate(prompt_list, start=1):
        print(f"\n🧠 Processing prompt {i}/{len(prompt_list)}...")

        graph_summary = summarize_graph_enhanced(nodes)
        context = _make_context_snippets(retrieved, max_chars=15000)
        
        # Format additional context
        metrics_summary = format_metrics_summary(metrics or {})
        processes_summary = format_business_processes(business_processes or [])
        mapping_summary = format_power_platform_mapping(power_platform_mapping or {})
        
        messages = [
            {"role": "system", "content": prompt},
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
        # Generate BRD content
        # brd_content = _chat(messages, temperature=0.1)

        try:
            response = _chat(messages, temperature=temperature)
            results.append(response.strip())
            print(f"✅ Prompt {i} completed successfully ({len(response)} chars).")
        except Exception as e:
            print(f"❌ Prompt {i} failed: {e}")
            results.append(f"[Error in prompt {i}: {e}]")

    # Combine all outputs into one final message
    print("\n🧩 Combining all partial outputs into one response...")
    combined_output = "\n\n".join(
        [f"Response {i}:\n{res}" for i, res in enumerate(results, 1)]
    )

    final_output = combined_output 



# calling 

brd_content = run_prompt_array(
                        array,
                        seed_results,
                        parsed["nodes"],
                        parsed.get("metrics"),
                        parsed.get("business_processes"),
                        power_mapping
                    )
