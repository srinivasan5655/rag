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

# UPDATED 
def run_prompt_array(prompt_list: List[str],
                     retrieved: List[Dict[str, Any]], 
                     nodes: List[Dict[str, Any]], 
                     metrics: Dict[str, Any] = None,
                     business_processes: List[Dict[str, Any]] = None,
                     power_platform_mapping: Dict[str, Any] = None, 
                     system_prompt: str = "", 
                     temperature: float = 0.1,
                     max_retries: int = 5) -> str:
    """
    Execute multiple prompts sequentially with retry, rate-limit handling,
    and progress visualization.
    """
    if not prompt_list:
        return "⚠️ No prompts provided."

    print(f"\n🚀 Running {len(prompt_list)} prompts sequentially...\n")
    results = []

    # tqdm progress bar
    pbar = tqdm(total=len(prompt_list), desc="Processing prompts", unit="prompt")

    for i, prompt in enumerate(prompt_list, start=1):
        print(f"\n🧠 Processing prompt {i}/{len(prompt_list)}...")
        start_time = time.time()
        graph_summary = summarize_graph_enhanced(nodes)
        context = _make_context_snippets(retrieved, max_chars=15000)
        
        metrics_summary = format_metrics_summary(metrics or {})
        processes_summary = format_business_processes(business_processes or [])
        mapping_summary = format_power_platform_mapping(power_platform_mapping or {})

        messages = [
            {"role": "system", "content": base + prompt},
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

        retries = 0
        success = False

        while retries < max_retries:
            try:
                response = _chat(messages, temperature=temperature)
                results.append(response.strip())
                elapsed = time.time() - start_time
                pbar.set_postfix_str(f"✅ Prompt {i} done ({elapsed:.1f}s)")
                success = True
                break

            except Exception as e:
                error_text = str(e).lower()
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
            results.append(f"[Rate limit exceeded or failed after {max_retries} retries]")
            pbar.set_postfix_str("❌ Max retries exceeded")

        pbar.update(1)
        time.sleep(0.5)  # small delay to keep UI smooth

    pbar.close()

    # Combine all responses
    print("\n🧩 Combining all partial outputs into one response...")
    combined_output = "\n\n".join(
        [f"Response {i}:\n{res}" for i, res in enumerate(results, 1)]
    )

    return combined_output



