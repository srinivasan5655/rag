# enhanced_app.py
import time
import os, tempfile, zipfile, io,base64
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from dotenv import load_dotenv
from utils import CODE_EXTS
from code_parser import parse_repository_enhanced
from rag_index import build_faiss_index, load_index, query
from io import BytesIO
from docx import Document
from brd_generator import (
    generate_brd,
    generate_complexity_analysis,
    generate_business_process_flows,
    generate_power_platform_detailed_mapping,
    generate_user_stories,
    answer_question_enhanced,
    generate_business_flows,
    generate_tables_analysis,
    generate_user_journeys,
    generate_personas,
    generate_user_storie,
    generate_test_cases,
    generate_complete_brd_async,
    generate_word_brd
)
from graph_store import GraphStore

load_dotenv()
st.set_page_config(
    page_title=".NET to Power Platform Modernization", 
    page_icon="⚡", 
    layout="wide"
)

# Custom CSS for better styling
st.markdown("""
<style>
.metric-card {
    background-color: #f0f2f6;
    padding: 1rem;
    border-radius: 0.5rem;
    margin: 0.5rem 0;
}
.risk-high { color: #e74c3c; font-weight: bold; }
.risk-medium { color: #f39c12; font-weight: bold; }
.risk-low { color: #27ae60; font-weight: bold; }
</style>
""", unsafe_allow_html=True)

st.title("⚡ .NET to Power Platform Migration Assistant")
st.caption("Comprehensive analysis of legacy .NET applications for Power Platform modernization")

# Sidebar Configuration
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
    rebuild_index = st.button("🔄 Build Vector Index", type="primary")
    clear_data = st.button("🗑️ Clear Session Data")
    
    if clear_data:
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.success("Session data cleared!")
        st.rerun()

# Initialize working directory
workdir = tempfile.mkdtemp(prefix="repo_analysis_")

# Main tabs
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📁 Upload & Parse", 
    "📊 Code Analysis", 
    "🔄 Business Processes", 
    "⚡ Power Platform Mapping", 
    "💬 Q&A Assistant",
    "BRD & Docs"
])

with tab1:
    st.header("📁 Source Code Upload & Analysis")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Upload Repository")
        up_zip = st.file_uploader(
            "Upload a .zip of your repository", 
            type=["zip"], 
            accept_multiple_files=False
        )
        
        if up_zip:
            try:
                z = zipfile.ZipFile(io.BytesIO(up_zip.read()))
                z.extractall(workdir)
                st.success(f"✅ ZIP extracted to: {workdir}")
                
                # Show extracted files
                extracted_files = []
                for root, dirs, files in os.walk(workdir):
                    for file in files:
                        rel_path = os.path.relpath(os.path.join(root, file), workdir)
                        if any(rel_path.endswith(ext) for ext in CODE_EXTS):      
                            extracted_files.append(rel_path)
                
                st.info(f"Found {len(extracted_files)} code files")
                with st.expander("View extracted files"):
                    for f in sorted(extracted_files)[:50]:  # Show first 50
                        st.text(f)
                    if len(extracted_files) > 50:
                        st.text(f"... and {len(extracted_files) - 50} more files")
                        
            except Exception as e:
                st.error(f"Error extracting ZIP: {str(e)}")
    
    with col2:
        st.subheader("Upload Individual Files")
        up_files = st.file_uploader(
            "...or upload individual code files", 
            type=[e.lstrip(".") for e in CODE_EXTS], 
            accept_multiple_files=True
        )
        
        if up_files:
            try:
                for f in up_files:
                    dest = os.path.join(workdir, f.name)
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    with open(dest, "wb") as out:
                        out.write(f.read())
                st.success(f"✅ Saved {len(up_files)} files")
            except Exception as e:
                st.error(f"Error saving files: {str(e)}")
    
    # === NEW SECTION: Supporting Documents ===
    st.divider()
    st.subheader("📎 Upload Supporting Documents (optional)")
    
    doc_types = ["pdf", "docx", "xlsx", "csv", "txt", "md"]
    support_docs = st.file_uploader(
        "Upload additional documents such as BRDs, specs, or references",
        type=doc_types,
        accept_multiple_files=True
    )
    
    if support_docs:
        try:
            support_dir = os.path.join(workdir, "support_docs")
            os.makedirs(support_dir, exist_ok=True)
            
            saved_files = []
            for doc in support_docs:
                dest_path = os.path.join(support_dir, doc.name)
                with open(dest_path, "wb") as out:
                    out.write(doc.read())
                saved_files.append(doc.name)
            
            st.success(f"✅ Saved {len(saved_files)} supporting documents")
            with st.expander("View uploaded documents"):
                for f in saved_files:
                    st.text(f)
        except Exception as e:
            st.error(f"Error saving supporting documents: {str(e)}")
    
    st.divider()
    
    # Parse repository
    col1, col2 = st.columns([3, 1])
    with col1:
        st.subheader("🔍 Repository Analysis")
    with col2:
        parse_btn = st.button("🚀 Parse Repository", type="primary")
    
    if parse_btn:
        with st.spinner("Analyzing repository..."):
            try:
                parsed = parse_repository_enhanced(workdir, max_chunk, overlap)
                st.session_state["parsed"] = parsed
                
                # Quick summary
                col1, col2, col3, col4 = st.columns(4)
                with col1:
                    st.metric("Code Files", parsed["metrics"]["total"]["total_files"])
                with col2:
                    st.metric("Lines of Code", f"{parsed['metrics']['total']['total_loc']:,}")
                with col3:
                    st.metric("Components", len(parsed["nodes"]))
                with col4:
                    st.metric("Processes", len(parsed["business_processes"]))
                
                st.success("✅ Repository parsed successfully!")
                st.balloons()
                # st.snow()
                
                # Store in graph database
                if gremlin_enabled:
                    try:
                        gs = GraphStore()
                        gs.upsert_vertices(parsed["nodes"])
                        gs.upsert_edges(parsed["edges"])
                        st.info("📊 Graph data stored in Cosmos DB")
                    except Exception as e:
                        st.warning(f"Graph storage failed: {str(e)}")
                
            except Exception as e:
                st.error(f"Parsing failed: {str(e)}")

with tab2:
    st.header("📊 Code Complexity & Quality Analysis")
    
    parsed = st.session_state.get("parsed")
    if not parsed:
        st.warning("Please upload and parse a repository first!")
    else:
        metrics = parsed.get("metrics", {})
        total_metrics = metrics.get("total", {})
        file_metrics = metrics.get("by_file", {})
        
        # Overview metrics
        st.subheader("Repository Overview")
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.metric(
                "Total Files", 
                total_metrics.get("total_files", 0)
            )
        
        with col2:
            st.metric(
                "Lines of Code", 
                f"{total_metrics.get('total_loc', 0):,}"
            )
        
        with col3:
            avg_complexity = total_metrics.get('total_complexity', 0) / max(total_metrics.get('total_files', 1), 1)
            st.metric(
                "Avg Complexity", 
                f"{avg_complexity:.1f}",
                delta="High" if avg_complexity > 10 else "Normal"
            )
        
        with col4:
            maintainability = total_metrics.get('avg_maintainability', 0)
            st.metric(
                "Maintainability", 
                f"{maintainability:.1f}/100",
                delta="Good" if maintainability > 70 else "Poor"
            )
        
        # File type distribution
        st.subheader("File Type Distribution")
        if total_metrics.get('file_types'):
            file_types_df = pd.DataFrame([
                {"Extension": ext, "Count": count} 
                for ext, count in total_metrics['file_types'].items()
            ])
            
            fig = px.pie(
                file_types_df, 
                values="Count", 
                names="Extension", 
                title="Code Files by Type"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Complexity analysis
        st.subheader("Complexity Analysis")
        
        if file_metrics:
            # Prepare data for visualization
            complexity_data = []
            for file_path, file_data in file_metrics.items():
                complexity_data.append({
                    "File": os.path.basename(file_path),
                    "Full Path": file_path,
                    "Lines of Code": file_data.get("lines_of_code", 0),
                    "Complexity": file_data.get("cyclomatic_complexity", 0),
                    "Maintainability": file_data.get("maintainability_index", 0),
                    "Risk Level": (
                        "High" if (file_data.get("cyclomatic_complexity", 0) > 15 or 
                                 file_data.get("maintainability_index", 100) < 50)
                        else "Medium" if file_data.get("cyclomatic_complexity", 0) > 10
                        else "Low"
                    )
                })
            
            complexity_df = pd.DataFrame(complexity_data)
            
            # Complexity vs Maintainability scatter plot
            fig = px.scatter(
                complexity_df,
                x="Complexity",
                y="Maintainability",
                size="Lines of Code",
                color="Risk Level",
                hover_data=["File"],
                title="Code Complexity vs Maintainability",
                color_discrete_map={
                    "High": "#e74c3c",
                    "Medium": "#f39c12", 
                    "Low": "#27ae60"
                }
            )
            st.plotly_chart(fig, use_container_width=True)
            
            # High-risk files table
            high_risk_files = complexity_df[complexity_df["Risk Level"] == "High"].nlargest(10, "Complexity")
            
            if not high_risk_files.empty:
                st.subheader("🚨 High-Risk Files (Top 10)")
                st.dataframe(
                    high_risk_files[["File", "Lines of Code", "Complexity", "Maintainability", "Risk Level"]],
                    use_container_width=True
                )
            
            # Generate detailed analysis
            if st.button("📋 Generate Complexity Analysis Report"):
                with st.spinner("Generating complexity analysis..."):
                    complexity_report = generate_complexity_analysis(metrics, parsed["nodes"])
                    
                    st.subheader("Complexity Analysis Report")
                    st.markdown(complexity_report)
                    
                    st.download_button(
                        "💾 Download Report",
                        complexity_report,
                        "complexity_analysis.md",
                        mime="text/markdown"
                    )

with tab3:
    st.header("🔄 Business Process Analysis")
    
    parsed = st.session_state.get("parsed")
    if not parsed:
        st.warning("Please upload and parse a repository first!")
    else:
        business_processes = parsed.get("business_processes", [])
        
        if not business_processes:
            st.info("No business processes detected in the codebase.")
        else:
            # Process overview
            st.subheader("Detected Business Processes")
            
            process_summary = []
            for process in business_processes:
                #process_summary.append({
                #    "Process Name": process["name"],
                #    "Controller": process["controller"],
                #    "Actions": process["total_actions"],
                #    "Complexity": process["complexity"],
                #    "CRUD Operations": len([ops for ops in process["crud_operations"].values() if ops]),
                #    "Workflow Steps": len(process.get("workflow_steps", []))
                #})
                process_summary.append({
    "Process Name": process["name"],
    "Source": process.get("source", "unknown"),  # ✅ Show source instead
    "Controller": process.get("controller", "N/A"),  # ✅ Use .get() with default
    "Actions": process.get("total_actions", len(process.get("workflow_steps", []))),  # ✅ Handle both types
    "Complexity": process["complexity"],
    "CRUD Operations": len([ops for ops in process.get("crud_operations", {}).values() if ops]),
    "Workflow Steps": len(process.get("workflow_steps", []))
})
            
            process_df = pd.DataFrame(process_summary)
            st.dataframe(process_df, use_container_width=True)
            
            # Process complexity visualization
            fig = px.bar(
                process_df,
                x="Process Name",
                y="Actions",
                color="Complexity",
                title="Business Process Complexity",
                color_discrete_map={
                    "High": "#e74c3c",
                    "Medium": "#f39c12",
                    "Low": "#27ae60"
                }
            )
            #fig.update_xaxis(tickangle=45)
            fig.update_layout(xaxis=dict(tickangle=45))

            st.plotly_chart(fig, use_container_width=True)
            
            # Detailed process analysis
            st.subheader("Process Details")
            selected_process = st.selectbox(
                "Select a process for detailed analysis:",
                options=[p["name"] for p in business_processes]
            )
            
            if selected_process:
                process = next(p for p in business_processes if p["name"] == selected_process)
                
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**CRUD Operations:**")
                    for operation, actions in process["crud_operations"].items():
                        if actions:
                            st.write(f"- {operation}: {', '.join(actions)}")
                
                with col2:
                    if process.get("workflow_steps"):
                        st.write("**Workflow Steps:**")
                        for step in process["workflow_steps"]:
                            roles_text = f" ({', '.join(step['roles'])})" if step['roles'] else ""
                            st.write(f"- {step['step']} ({step['type']}){roles_text}")
            
            # Generate detailed BPF documentation
            if st.button("📄 Generate Business Process Flow Documentation"):
                with st.spinner("Generating BPF documentation..."):
                    bpf_docs = generate_business_process_flows(business_processes, parsed["nodes"])
                    
                    st.subheader("Business Process Flow Documentation")
                    st.markdown(bpf_docs)
                    
                    st.download_button(
                        "💾 Download BPF Documentation",
                        bpf_docs,
                        "business_process_flows.md",
                        mime="text/markdown"
                    )

with tab4:
    st.header("⚡ Power Platform Migration Mapping")
    
    parsed = st.session_state.get("parsed")
    if not parsed:
        st.warning("Please upload and parse a repository first!")
    else:
        power_mapping = parsed.get("power_platform_mapping", {})
        
        # Dataverse Tables
        st.subheader("📊 Dataverse Table Mapping")
        dataverse_tables = power_mapping.get("dataverse_tables", [])
        
        if dataverse_tables:
            table_summary = []
            for table in dataverse_tables:
            

                table_summary.append({
    "Legacy Entity": table["legacy_entity"],
    "Dataverse Table": table["suggested_table_name"],
    "Display Name": table.get("display_name", table["legacy_entity"]),
    "Schema": table.get("schema", "dbo"),
    "Columns": len(table.get("columns", [])),
    "Sources": ", ".join(table.get("sources", ["Unknown"])),  # ✅ Show all sources
    "Confidence": f"{table.get('confidence', 0):.0%}",  # ✅ Show confidence score
    "Needs Review": "⚠️ Yes" if table.get("needs_review") else "✅ No"  # ✅ Flag low confidence
})
            
            table_df = pd.DataFrame(table_summary)
            st.dataframe(table_df, use_container_width=True)
            
            # Detailed table view
            selected_table = st.selectbox(
                "Select a table for detailed column mapping:",
                options=[t["legacy_entity"] for t in dataverse_tables]
            )
            
            if selected_table:
                table_detail = next(t for t in dataverse_tables if t["legacy_entity"] == selected_table)
                columns = table_detail.get("columns", [])
                
                if columns:
                    column_data = []
                    for col in columns:
                        column_data.append({
                            "Column Name": col["name"],
                            "Dataverse Type": col["type"],
                            "Required": "Yes" if col["required"] else "No",
                            "Max Length": col.get("max_length", "N/A"),
                            "Original Type": col["original_type"]
                        })
                    
                    column_df = pd.DataFrame(column_data)
                    st.subheader(f"Column Details: {selected_table}")
                    st.dataframe(column_df, use_container_width=True)
        else:
            st.info("No entities detected for Dataverse mapping.")
        
        # Power Apps Screens
        st.subheader("📱 Power Apps Screen Mapping")
        power_apps_screens = power_mapping.get("power_apps_screens", [])
        
        if power_apps_screens:
            screen_summary = []
            for screen in power_apps_screens:
              

                screen_summary.append({
    "Legacy View": screen["legacy_view"],
    "Screen Type": screen["screen_type"],
    "Fields": len(screen.get("fields", [])),
    "Data Sources": ", ".join(screen.get("data_sources", [])) if screen.get("data_sources") else "N/A",
    "Controller": screen.get("controller", "N/A"),
    "Action": screen.get("action", "N/A"),
    "Source File": screen.get("source_file", "N/A")  # ✅ Now with safe access
})
            
            screen_df = pd.DataFrame(screen_summary)
            st.dataframe(screen_df, use_container_width=True)
            
            # Screen type distribution
            screen_type_counts = screen_df["Screen Type"].value_counts()
            fig = px.pie(
                values=screen_type_counts.values,
                names=screen_type_counts.index,
                title="Power Apps Screen Type Distribution"
            )
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No views detected for Power Apps mapping.")
        
        # Power Automate Flows
        st.subheader("🔄 Power Automate Flow Recommendations")
        power_automate_flows = power_mapping.get("power_automate_flows", [])
        
        if power_automate_flows:
            flow_summary = []
            for flow in power_automate_flows:
                flow_summary.append({
                    "Flow Name": flow["name"],
                    "Trigger": flow["trigger"],
                    "Steps": len(flow.get("steps", [])),
                    "Business Process": flow["business_process"]
                })
            
            flow_df = pd.DataFrame(flow_summary)
            st.dataframe(flow_df, use_container_width=True)
            
            # Detailed flow view
            selected_flow = st.selectbox(
                "Select a flow for detailed steps:",
                options=[f["name"] for f in power_automate_flows]
            )
            
            if selected_flow:
                flow_detail = next(f for f in power_automate_flows if f["name"] == selected_flow)
                steps = flow_detail.get("steps", [])
                
                if steps:
                    st.subheader(f"Flow Steps: {selected_flow}")
                    for i, step in enumerate(steps, 1):
                        st.write(f"**Step {i}: {step['type']}**")
                        st.write(f"- {step['description']}")
                        if step.get("assignees"):
                            st.write(f"- Assignees: {', '.join(step['assignees'])}")
        else:
            st.info("No workflow processes detected for Power Automate.")
        
        # Generate comprehensive mapping
        col1, col2 = st.columns(2)
        
        with col1:
            if st.button("📋 Generate Detailed Power Platform Mapping"):
                with st.spinner("Generating detailed mapping..."):
                    detailed_mapping = generate_power_platform_detailed_mapping(
                        power_mapping, 
                        parsed["nodes"], 
                        parsed.get("business_processes", [])
                    )
                    
                    st.subheader("Detailed Power Platform Mapping")
                    st.markdown(detailed_mapping)

                    word_file = generate_word_brd(detailed_mapping, 'Power Platform Mapping')

                    st.download_button(
                        "💾 Download Mapping",
                        word_file,
                        # f"Complete_BRD_{app_name.replace(' ', '_')}.docx",
                        "power_platform_mapping.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )
                    
                    # st.download_button(
                    #     "💾 Download Mapping",
                    #     detailed_mapping,
                    #     "power_platform_mapping.md",
                    #     mime="text/markdown"
                    # )
        
        with col2:
            if st.button("📝 Generate User Stories"):
                with st.spinner("Generating user stories..."):
                    user_stories = generate_user_stories(
                        parsed.get("business_processes", []),
                        parsed["nodes"],
                        power_mapping
                    )
                    
                    st.subheader("User Stories for Power Platform Development")
                    st.markdown(user_stories)
                    
                    word_file = generate_word_brd(user_stories, 'User Stories')

                    st.download_button(
                        "💾 Download User Stories",
                        word_file,
                        # f"Complete_BRD_{app_name.replace(' ', '_')}.docx",
                        "user_stories.docx",
                        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        use_container_width=True
                    )

                    # st.download_button(
                    #     "💾 Download User Stories",
                    #     user_stories,
                    #     "user_stories.md",
                    #     mime="text/markdown"
                    # )
        
        # Complete BRD Generation
        st.divider()
        st.subheader("📄 Complete Business Requirements Document")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            st.write("Generate a comprehensive BRD with all analysis results")
        with col2:
            generate_brd_btn = st.button("Generate Complete BRD", type="primary")

           
        if generate_brd_btn:
            # Build vector index if not exists
            if not os.path.exists(index_path):
                with st.spinner("Building vector index..."):
                    build_faiss_index(parsed["chunks"], index_path)
            
            # Load index and generate BRD
            with st.spinner("Generating comprehensive BRD..."):
                status_placeholder = st.empty()
                try:
                    
                    status_placeholder.text("Loading vector index...")
                    idx, texts, meta ,tokenized, vecs= load_index(index_path)
                    print('after load index')
                    # Get comprehensive context
                    status_placeholder.text("Retrieving context for BRD generation...")
                    seed_results = query(idx, texts, meta, 
                                       "overview main modules data access business processes controllers", 
                                       top_k=15)
                    
                    # print(seed_results)
                    # status.text("Generating Business Flows...")
                    status_placeholder.text("Generating Business Requirements Document...")
                    print('before generate brd')
                    brd_content = generate_brd(
                        seed_results,
                        parsed["nodes"],
                        parsed.get("metrics"),
                        parsed.get("business_processes"),
                        power_mapping
                    )
                    print('after generate brd')
                    st.subheader("📋 Business Requirements Document")
                    status_placeholder.text("")
                    st.markdown(brd_content)
                    
                    # Download options
                    col1, col2, col3 = st.columns(3)
                    with col1:
                        # st.download_button(
                        #     "💾 Download BRD (Markdown)",
                        #     brd_content,
                        #     "BusinessRequirementsDocument.md",
                        #     mime="text/markdown"
                        # )
                        word_file = generate_word_brd(brd_content, 'Complete_BRD')
                        st.balloons()
                        st.download_button(
                            "⬇️ Download Complete BRD (Word)",
                            word_file,
                            # f"Complete_BRD_{app_name.replace(' ', '_')}.docx",
                            "Complete_BRD.docx",
                            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            use_container_width=True
                        )
                    
                    with col2:
                        # Convert to HTML for better formatting
                        html_content = f"""
                        <html><head><title>Business Requirements Document</title>
                        <style>body{{font-family: Arial, sans-serif; margin: 40px;}}</style>
                        </head><body>{brd_content}</body></html>
                        """
                        st.download_button(
                            "💾 Download BRD (HTML)",
                            html_content,
                            "BusinessRequirementsDocument.html",
                            mime="text/html"
                        )
                    
                    with col3:
                        # Create summary metrics
                        summary_data = {
                            "Total Files": parsed["metrics"]["total"]["total_files"],
                            "Lines of Code": parsed["metrics"]["total"]["total_loc"],
                            "Components": len(parsed["nodes"]),
                            "Business Processes": len(parsed.get("business_processes", [])),
                            "Dataverse Tables": len(power_mapping.get("dataverse_tables", [])),
                            "Power Apps Screens": len(power_mapping.get("power_apps_screens", [])),
                            "Power Automate Flows": len(power_mapping.get("power_automate_flows", []))
                        }
                        
                        summary_text = "\n".join([f"{k}: {v}" for k, v in summary_data.items()])
                        st.download_button(
                            "📊 Download Summary",
                            summary_text,
                            "migration_summary.txt",
                            mime="text/plain"
                        )
                
                except Exception as e:
                    st.error(f"BRD generation failed: {str(e)}")

with tab5:
    st.header("💬 Q&A Assistant")
    
    parsed = st.session_state.get("parsed")
    if not parsed:
        st.warning("Please upload and parse a repository first!")
    else:
        # Build/load vector index
        if not os.path.exists(index_path) or rebuild_index:
            with st.spinner("Building vector index for Q&A..."):
                build_faiss_index(parsed["chunks"], index_path, parsed.get("supporting_docs", []))
                st.success("✅ Vector index ready!")
        
        if os.path.exists(index_path):
            try:
                idx, texts, meta ,tokenized, vecs = load_index(index_path)
                st.success(f"🔍 Vector index loaded ({len(texts)} chunks)")
                
                # Q&A Interface
                st.subheader("Ask Questions About Your Application")
                
                # Sample questions
                st.write("**Sample Questions:**")
                sample_questions = [
                    "What are the main business processes in this application?",
                    "Which files have the highest complexity?",
                    "What entities should be migrated to Dataverse?",
                    "What approval workflows exist in the system?",
                    "What security roles are defined?",
                    "Which components will be most challenging to migrate?",
                    "What Power Apps screens should be created?",
                    "What integrations exist with external systems?"
                ]
                
                selected_sample = st.selectbox(
                    "Select a sample question or type your own:",
                    [""] + sample_questions
                )
                
                # Question input
                question = st.text_input(
                    "Your question:",
                    value=selected_sample,
                    placeholder="Ask anything about the application architecture, complexity, or Power Platform migration..."
                )
                
                col1, col2 = st.columns([1, 4])
                with col1:
                    search_btn = st.button("🔍 Search & Answer", type="primary")
                with col2:
                    show_context = st.checkbox("Show retrieved context", value=False)
                
                if search_btn and question.strip():
                    with st.spinner("Searching and analyzing..."):
                        try:
                            # Enhanced search with higher top-k for complex questions
                            top_k = 10 if any(word in question.lower() for word in 
                                            ['complex', 'process', 'workflow', 'migration', 'all']) else 6
                            
                            results = query(idx, texts, meta, question, top_k=top_k)
                            
                            if show_context:
                                st.subheader("📄 Retrieved Context")
                                with st.expander(f"Top {len(results)} relevant code sections"):
                                    for i, r in enumerate(results):
                                        st.markdown(f"**Result {i+1}** - {r.get('meta',{}).get('path', '?')} (Score: {r['score']:.3f})")
                                        st.code(r["text"][:1000] + "..." if len(r["text"]) > 1000 else r["text"])
                                        st.divider()
                            
                            # Generate enhanced answer
                            answer = answer_question_enhanced(
                                question,
                                results,
                                parsed["nodes"],
                                parsed.get("metrics"),
                                parsed.get("business_processes")
                            )
                            
                            st.subheader("💡 Answer")
                            st.markdown(answer)
                            
                            # Save Q&A to session for context
                            if "qa_history" not in st.session_state:
                                st.session_state.qa_history = []
                            
                            st.session_state.qa_history.append({
                                "question": question,
                                "answer": answer,
                                "timestamp": pd.Timestamp.now()
                            })
                            
                        except Exception as e:
                            st.error(f"Q&A failed: {str(e)}")
                
                # Q&A History
                if "qa_history" in st.session_state and st.session_state.qa_history:
                    st.divider()
                    st.subheader("📚 Q&A History")
                    
                    for i, qa in enumerate(reversed(st.session_state.qa_history[-5:]), 1):
                        with st.expander(f"Q{i}: {qa['question'][:60]}..."):
                            st.markdown(f"**Question:** {qa['question']}")
                            st.markdown(f"**Answer:** {qa['answer']}")
                            st.caption(f"Asked at: {qa['timestamp']}")
                
            except Exception as e:
                st.error(f"Failed to load vector index: {str(e)}")

# with tab6:
#     st.header("📄 BRD & Documentation Generator")
    
#     parsed = st.session_state.get("parsed")
#     if not parsed:
#         st.warning("Please upload and parse a repository first!")
#     else:
#         # Application name input
#         app_name = st.text_input(
#             "Application Name", 
#             value="Legacy .NET Application",
#             help="Enter the name of your application for document generation"
#         )
        
#         st.divider()
        
#         # Document selection with better layout
#         st.subheader("📋 Select Documents to Generate")
        
#         col1, col2 = st.columns(2)
        
#         with col1:
#             st.markdown("**Process & Architecture**")
#             gen_business_flows = st.checkbox("Business Process Flows", value=False)
#             gen_tables = st.checkbox("Database & Dataverse Mapping", value=False)
#             gen_user_journeys = st.checkbox("User Journeys", value=False)
        
#         with col2:
#             st.markdown("**User Experience & Testing**")
#             gen_personas = st.checkbox("Personas", value=False)
#             gen_user_stories = st.checkbox("User Stories", value=False)
#             gen_test_cases = st.checkbox("Functional Test Cases", value=False)
        
#         st.divider()
        
#         # Complete BRD option
#         st.subheader("📄 Complete Documentation Package")
#         gen_complete_brd = st.checkbox(
#             "Generate Complete BRD (includes all sections above)", 
#             value=False,
#             help="This will generate a comprehensive document with all sections"
#         )
        
#         st.divider()
        
#         # Prepare analysis data
#         seed_results = query(idx, texts, meta, 
#                 "overview main modules data access business processes controllers", 
#                 top_k=15)
                            
#         analysis_data = (        
#             seed_results,
#             parsed["nodes"],
#             parsed.get("metrics"),
#             parsed.get("business_processes"),
#             power_mapping
#         )
        
#         # Generation buttons
#         st.subheader("🚀 Generate & Download")
        
#         col1, col2, col3 = st.columns(3)
        
#         # Business Process Flows
#         if gen_business_flows:
#             with col1:
#                 if st.button("📊 Generate Business Flows", use_container_width=True):
#                     with st.spinner("Generating Business Process Flows..."):
#                         try:
#                             idx, texts, meta = load_index(index_path)

#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            
#                             import asyncio
#                             content = asyncio.run(
#                                 generate_business_flows(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
#                             )
                            
#                             st.success("✅ Business Flows generated!")
#                             st.download_button(
#                                 "⬇️ Download Business Flows",
#                                 content,
#                                 f"Business_Flows_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # Database Mapping
#         if gen_tables:
#             with col2:
#                 if st.button("🗄️ Generate DB Mapping", use_container_width=True):
#                     with st.spinner("Generating Database Mapping..."):
#                         try:
#                             idx, texts, meta = load_index(index_path)

#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            
#                             import asyncio
#                             content = asyncio.run(
#                                 generate_tables_analysis(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
#                             )
                            
#                             st.success("✅ Database Mapping generated!")
#                             st.download_button(
#                                 "⬇️ Download DB Mapping",
#                                 content,
#                                 f"Database_Mapping_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # User Journeys
#         if gen_user_journeys:
#             with col3:
#                 if st.button("🗺️ Generate User Journeys", use_container_width=True):
#                     with st.spinner("Generating User Journeys..."):
#                         try:
#                             idx, texts, meta = load_index(index_path)

#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            
#                             import asyncio
#                             content = asyncio.run(
#                                 generate_user_journeys(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
#                             )
                            
#                             st.success("✅ User Journeys generated!")
#                             st.download_button(
#                                 "⬇️ Download User Journeys",
#                                 content,
#                                 f"User_Journeys_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # Second row
#         col1, col2, col3 = st.columns(3)
        
#         # Personas
#         if gen_personas:
#             with col1:
#                 if st.button("👥 Generate Personas", use_container_width=True):
#                     with st.spinner("Generating Personas..."):
#                         try:

#                             idx, texts, meta = load_index(index_path)

#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            
#                             import asyncio
#                             content = asyncio.run(
#                                 generate_personas(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
#                             )
                            
#                             st.success("✅ Personas generated!")
#                             st.download_button(
#                                 "⬇️ Download Personas",
#                                 content,
#                                 f"Personas_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # User Stories
#         if gen_user_stories:
#             with col2:
#                 if st.button("📝 Generate User Stories", use_container_width=True):
#                     with st.spinner("Generating User Stories..."):
#                         try:
#                             content = generate_user_stories(
#                                 parsed.get("business_processes", []),
#                                 parsed["nodes"],
#                                 power_mapping
#                             )
                            
#                             st.subheader("User Stories for Power Platform Development")
#                             st.markdown(content)
                            
#                             # word_file = generate_word_brd(user_stories, 'User Stories')
                            
#                             st.success("✅ User Stories generated!")
#                             st.download_button(
#                                 "⬇️ Download User Stories",
#                                 content,
#                                 f"User_Stories_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # Test Cases
#         if gen_test_cases:
#             with col3:
#                 if st.button("✅ Generate Test Cases", use_container_width=True):
#                     with st.spinner("Generating Functional Test Cases..."):
#                         try:
#                             idx, texts, meta = load_index(index_path)

#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            
#                             import asyncio
#                             content = asyncio.run(
#                                 generate_test_cases(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
#                             )
                            
#                             st.success("✅ Test Cases generated!")
#                             st.download_button(
#                                 "⬇️ Download Test Cases",
#                                 content,
#                                 f"Test_Cases_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
#                         except Exception as e:
#                             st.error(f"Failed to generate: {str(e)}")
        
#         # Complete BRD Generation
#         if gen_complete_brd:
#             st.divider()
#             st.markdown("### 📦 Complete BRD Package")
            
#             col1, col2, col3 = st.columns([2, 2, 1])
            
#             with col1:
#                 st.info("This will generate a comprehensive document with all sections")
            
#             with col2:
#                 if st.button("🚀 Generate Complete BRD", type="primary", use_container_width=True):
#                     with st.spinner("Generating Complete BRD... This may take a few minutes."):
#                         try:
#                             status_placeholder.text("Loading vector index...")
#                             idx, texts, meta = load_index(index_path)
                            
#                             # Get comprehensive context
#                             status_placeholder.text("Retrieving context for BRD generation...")
#                             seed_results = query(idx, texts, meta, 
#                                             "overview main modules data access business processes controllers", 
#                                             top_k=15)
                            

#                             # status.text("Generating Business Flows...")
#                             status_placeholder.text("Thinking...")
#                             brd_content = generate_brd(
#                                 seed_results,
#                                 parsed["nodes"],
#                                 parsed.get("metrics"),
#                                 parsed.get("business_processes"),
#                                 power_mapping
#                             )
                            
#                             st.success("✅ Complete BRD generated successfully!")
                            
#                             # Show preview
#                             with st.expander("📄 Preview BRD Content"):
#                                 st.markdown(content[:2000] + "..." if len(content) > 2000 else content)
                            
#                             # Download button
#                             st.download_button(
#                                 "⬇️ Download Complete BRD",
#                                 content,
#                                 f"Complete_BRD_{app_name.replace(' ', '_')}.md",
#                                 "text/markdown",
#                                 use_container_width=True
#                             )
                            
#                             # Also offer HTML version
#                             html_content = f"""
#                             <!DOCTYPE html>
#                             <html>
#                             <head>
#                                 <meta charset="UTF-8">
#                                 <title>Business Requirements Document - {app_name}</title>
#                                 <style>
#                                     body {{
#                                         font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
#                                         line-height: 1.6;
#                                         max-width: 1200px;
#                                         margin: 40px auto;
#                                         padding: 20px;
#                                         color: #333;
#                                     }}
#                                     h1 {{ color: #2c3e50; border-bottom: 3px solid #3498db; padding-bottom: 10px; }}
#                                     h2 {{ color: #2980b9; margin-top: 30px; }}
#                                     h3 {{ color: #34495e; }}
#                                     table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
#                                     th, td {{ border: 1px solid #ddd; padding: 12px; text-align: left; }}
#                                     th {{ background-color: #3498db; color: white; }}
#                                     code {{ background-color: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
#                                     pre {{ background-color: #f4f4f4; padding: 15px; border-radius: 5px; overflow-x: auto; }}
#                                     .metric {{ background-color: #ecf0f1; padding: 10px; border-radius: 5px; margin: 10px 0; }}
#                                 </style>
#                             </head>
#                             <body>
#                                 {content.replace('```', '<pre>').replace('# ', '<h1>').replace('## ', '<h2>').replace('### ', '<h3>')}
#                             </body>
#                             </html>
#                             """
                            
#                             st.download_button(
#                                 "⬇️ Download Complete BRD (HTML)",
#                                 html_content,
#                                 f"Complete_BRD_{app_name.replace(' ', '_')}.html",
#                                 "text/html",
#                                 use_container_width=True
#                             )
                            
#                         except Exception as e:
#                             st.error(f"Failed to generate Complete BRD: {str(e)}")
#                             st.exception(e)
        
#         # Batch Generation Option
#         st.divider()
#         st.subheader("⚡ Batch Generation")
        
#         if st.button("📦 Generate All Selected Documents", type="secondary"):
#             selected_docs = []
#             if gen_business_flows:
#                 selected_docs.append(("Business Process Flows", generate_business_flows))
#             if gen_tables:
#                 selected_docs.append(("Database & Dataverse Mapping", generate_tables_analysis))
#             if gen_user_journeys:
#                 selected_docs.append(("User Journeys", generate_user_journeys))
#             if gen_personas:
#                 selected_docs.append(("Personas", generate_personas))
#             if gen_user_stories:
#                 selected_docs.append(("User Stories", generate_user_stories))
#             if gen_test_cases:
#                 selected_docs.append(("Functional Test Cases", generate_test_cases))
            
#             if not selected_docs:
#                 st.warning("Please select at least one document type to generate")
#             else:
#                 progress_bar = st.progress(0)
#                 status_text = st.empty()
                
#                 import asyncio
#                 import zipfile
#                 from io import BytesIO
                
#                 # Create a ZIP file with all documents
#                 zip_buffer = BytesIO()
#                 with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
#                     for idx, (doc_name, generator_func) in enumerate(selected_docs):
#                         status_text.text(f"Generating {doc_name}...")
#                         progress = (idx + 1) / len(selected_docs)
#                         progress_bar.progress(progress)
                        
#                         try:
#                             content = asyncio.run(generator_func(            
#                             seed_results,
#                             parsed["nodes"],
#                             parsed.get("metrics"),
#                             parsed.get("business_processes"),
#                             power_mapping))
#                             filename = f"{doc_name.replace(' ', '_')}_{app_name.replace(' ', '_')}.md"
#                             zip_file.writestr(filename, content)
#                         except Exception as e:
#                             st.error(f"Failed to generate {doc_name}: {str(e)}")
                
#                 status_text.text("All documents generated!")
#                 progress_bar.progress(1.0)
                
#                 st.success(f"✅ Successfully generated {len(selected_docs)} documents!")
                
#                 # Download ZIP
#                 st.download_button(
#                     "⬇️ Download All Documents (ZIP)",
#                     zip_buffer.getvalue(),
#                     f"BRD_Documentation_{app_name.replace(' ', '_')}.zip",
#                     "application/zip",
#                     use_container_width=True
#                 )
        
#         # Documentation Info
#         st.divider()
#         with st.expander("ℹ️ Document Descriptions"):
#             st.markdown("""
#             **Business Process Flows**: Detailed workflows and process diagrams showing how business operations flow through the system.
            
#             **Database & Dataverse Mapping**: Complete mapping of legacy database schemas to Dataverse tables with field mappings and relationships.
            
#             **User Journeys**: Step-by-step user interaction flows showing how different user types navigate and use the system.
            
#             **Personas**: Detailed user personas representing different types of users, their goals, pain points, and requirements.
            
#             **User Stories**: Agile user stories with acceptance criteria for Power Platform development.
            
#             **Functional Test Cases**: Comprehensive test scenarios to validate the migrated Power Platform solution.
            
#             **Complete BRD**: A comprehensive document combining all sections above into a single Business Requirements Document.
#             """)

#     # if complete_brd:
#     #     if st.button("🚀 Generate Complete BRD", type="primary"):
#     #         with st.spinner("Generating Complete BRD..."):
#     #             import asyncio
#     #             content = asyncio.run(generate_complete_brd_async(analysis_data))

#     #             # Encode file content to Base64
#     #             b64 = base64.b64encode(content.encode()).decode()
#     #             filename = f"Complete_BRD_{app_name.replace(' ', '_')}.md"

#     #             # Inject JavaScript to auto-trigger download
#     #             js = f"""
#     #             <script>
#     #             const link = document.createElement('a');
#     #             link.href = "data:text/markdown;base64,{b64}";
#     #             link.download = "{filename}";
#     #             document.body.appendChild(link);
#     #             link.click();
#     #             document.body.removeChild(link);
#     #             </script>
#     #             """
#     #             st.success("✅ BRD Generated and downloading automatically...")
#     #             st.markdown(js, unsafe_allow_html=True)

#     # if complete_brd:
#     #     if st.button("🚀 Generate Complete BRD", type="primary"):
#     #         with st.spinner("Generating Complete BRD..."):
#     #             import asyncio
#     #             content = asyncio.run(generate_complete_brd_async(analysis_data))
                
#     #             # Encode to base64 for direct download
#     #             b64 = base64.b64encode(content.encode()).decode()
#     #             href = f'<a href="data:text/markdown;base64,{b64}" download="Complete_BRD_{app_name.replace(" ", "_")}.md">📥 Download Complete BRD</a>'
                
#     #             st.success("✅ BRD Generated Successfully!")
#     #             st.markdown(href, unsafe_allow_html=True)

# TAB 9: Migration Insights Dashboard
# Footer
st.divider()
col1, col2, col3 = st.columns(3)

with col1:
    st.caption("🔧 **Tech Stack:** Azure OpenAI, FAISS, Streamlit, Cosmos DB")

with col2:
    if parsed:
        total_files = parsed["metrics"]["total"]["total_files"]
        total_loc = parsed["metrics"]["total"]["total_loc"]
        st.caption(f"📊 **Current Analysis:** {total_files} files, {total_loc:,} LOC")

with col3:
    st.caption("⚡ **Target:** Power Platform (Power Apps, Power Automate, Dataverse)")

# Help section
with st.sidebar:
    st.divider()
    st.subheader("ℹ️ Help")
    with st.expander("How to use this tool"):
        st.markdown("""
        1. **Upload** your .NET repository (.zip) or individual files
        2. **Parse** the repository to analyze code structure  
        3. **Review** complexity metrics and business processes
        4. **Explore** Power Platform mapping recommendations
        5. **Generate** comprehensive BRD and user stories
        6. **Ask** questions about your application using the Q&A assistant
        
        The tool analyzes C#, ASP.NET MVC, Entity Framework, SQL, and Angular code to provide migration guidance for Power Platform.
        """)
    
    with st.expander("Configuration"):
        st.markdown("""
        Set up your `.env` file with:
        ```
        AZURE_OPENAI_API_KEY=your_key
        AZURE_OPENAI_ENDPOINT=your_endpoint  
        AZURE_OPENAI_DEPLOYMENT=your_deployment
        AZURE_OPENAI_EMBEDDING_DEPLOYMENT=your_embedding
        
        # Optional: Cosmos Gremlin for graph storage
        COSMOS_GREMLIN_ENDPOINT=your_endpoint
        COSMOS_GREMLIN_PRIMARY_KEY=your_key
        COSMOS_GREMLIN_DATABASE=your_db
        COSMOS_GREMLIN_GRAPH=your_graph
        ```
        """)