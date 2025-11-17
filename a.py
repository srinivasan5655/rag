
            if ext == '.sql':
                try:
                    with open(rel, 'r', encoding='utf-8', errors='ignore') as fh:
                        sql_text = fh.read()
                except Exception:
                    continue

                # Find all CREATE TABLE blocks (non-greedy until ')' followed by optional semicolon)
                create_blocks = re.findall(r'CREATE\s+TABLE\s+.*?\)\s*;', sql_text, re.IGNORECASE | re.DOTALL)
                if not create_blocks:
                    # try alternate pattern without semicolon terminator
                    create_blocks = re.findall(r'CREATE\s+TABLE\s+.*?\)\s*(?=\n|$)', sql_text, re.IGNORECASE | re.DOTALL)

                for block in create_blocks:
                    info = parse_create_table_block(block)
                    if not info or not info.get('table_name'):
                        continue
                    table_name = info['table_name']
                    # create node id (use your existing node creation utility - adapt name if different)
                    node_id = f"sqltable::{table_name}::{rel}"
                    # ensure unique id (you may prefer a hash like sha1)
                    # Save node into your nodes list in the same shape your parser uses
                    node = {
                        "id": node_id,
                        "name": table_name,
                        "label": table_name,
                        "kind": "sql_table",
                        "file": rel,
                        "props": {
                            "source": "SQL_DDL",
                            "table_name": table_name,
                            "schema": info.get("schema", "dbo"),
                            "columns": info.get("columns", []),
                            "table_level_foreign_keys": info.get("table_level_foreign_keys", []),
                            "ddl": block
                        }
                    }
                    # append to nodes (your parser probably has a function to add nodes; adapt accordingly)
                    nodes.append(node)





def generate_dot(retrieved: List[Dict[str, Any]],
                 diagram_type: str,
                 nodes: List[Dict[str, Any]],
                 metrics: Dict[str, Any] = None,
                 business_processes: List[Dict[str, Any]] = None,
                 power_platform_mapping: Dict[str, Any] = None,
                 ) -> str:
    """
    Generate Graphviz DOT for diagrams.

    For ER Diagrams: prefer SQL CREATE TABLE-derived nodes only (kind == 'sql_table').
    show all the columns in each table node.
    Build deterministic DOT from the SQL metadata (columns, PKs, inferred FKs).
    strictly show the relationships between tables using arrows while generating dot.
    If no SQL tables are available, fall back to original LLM-based generator.
    """
    try:
        # Prefer deterministic ER generation for ER Diagram requests
        if diagram_type and 'er' in diagram_type.lower():
            # Gather SQL tables from parsed nodes (only sql_table)
            sql_nodes = []
            for n in nodes or []:
                kind = (n.get('kind') or n.get('type') or '') or ''
                props = n.get('props') or {}
                if kind == 'sql_table' or props.get('source') == 'SQL_DDL' or n.get('source') == 'SQL_DDL':
                    sql_nodes.append(n)

            # Defensive additional checks if none found
            if not sql_nodes:
                for n in nodes or []:
                    props = n.get('props') or {}
                    label = (n.get('label') or n.get('name') or '') or ''
                    if props.get('source') == 'SQL_DDL' or (isinstance(label, str) and label.lower().endswith('_table')):
                        sql_nodes.append(n)

            # If we found SQL tables, construct DOT directly
            if sql_nodes:
                # Helper to safely get columns list from node
                def _get_columns_from_node(node):
                    props = node.get('props', {}) or {}
                    cols = props.get('columns') or node.get('columns') or props.get('schema_columns') or []
                    normalized = []
                    for c in cols or []:
                        if isinstance(c, dict):
                            normalized.append({
                                'name': c.get('name'),
                                'sql_type': c.get('sql_type') or c.get('type') or '',
                                'size': c.get('size'),
                                'is_primary_key': bool(c.get('is_primary_key') or c.get('primary') or c.get('pk')),
                                'required': bool(c.get('required') or ('NOT NULL' in (c.get('constraints') or '').upper())),
                                'references': c.get('references')
                            })
                        elif isinstance(c, (list, tuple)) and len(c) >= 1:
                            normalized.append({'name': c[0], 'sql_type': c[1] if len(c) > 1 else '', 'is_primary_key': False})
                        else:
                            cc = str(c)
                            parts = re.split(r'\s+', cc.strip())
                            if parts:
                                normalized.append({'name': parts[0], 'sql_type': parts[1] if len(parts) > 1 else '', 'is_primary_key': 'PRIMARY' in cc.upper()})
                    return [c for c in normalized if c.get('name')]

                # Build mapping name -> node for easy lookup
                table_map = {}
                tables = []
                for n in sql_nodes:
                    props = n.get('props', {}) or {}
                    label = n.get('label') or n.get('name') or n.get('table_name') or n.get('id') or 'UnknownTable'
                    table_name = props.get('table_name') or n.get('table_name') or label
                    display_name = str(table_name)
                    cols = _get_columns_from_node(n)
                    table_map[display_name.lower()] = display_name
                    tables.append({
                        'name': display_name,
                        'schema': props.get('schema') or n.get('schema') or 'dbo',
                        'columns': cols,
                        'node': n,
                        'raw_props': props
                    })

                # small helper singular/plural helpers
                def pluralize_s(name: str) -> str:
                    return name + 's'
                def pluralize_ies(name: str) -> str:
                    if name.endswith('y'):
                        return name[:-1] + 'ies'
                    return None

                # Heuristic to infer referenced table from column name
                def infer_referenced_table(col_name: str):
                    if not col_name:
                        return None
                    # common patterns: order_id, OrderId
                    if col_name.lower().endswith('_id'):
                        return col_name[:-3]
                    if col_name.endswith('Id') and len(col_name) > 2:
                        return col_name[:-2]
                    return None

                # Build DOT graph (record-based)
                dot_lines = []
                dot_lines.append('digraph ER {')
                dot_lines.append('  graph [rankdir="LR", fontsize=10];')
                dot_lines.append('  node [shape=record, fontname="Helvetica"];')
                dot_lines.append('')

                # Create nodes
                for t in tables:
                    cols = t['columns'] or []
                    col_lines = []
                    for c in cols:
                        name = c.get('name') or '(col)'
                        sqlt = c.get('sql_type') or ''
                        col_label = f"{name}: {sqlt}"
                        if c.get('is_primary_key'):
                            col_label = f"PK {col_label}"
                        if c.get('required'):
                            col_label = f"{col_label} [NOT NULL]"
                        # escape pipe and braces which break record label formatting
                        safe_label = col_label.replace('|', '\\|').replace('{', '\\{').replace('}', '\\}')
                        col_lines.append(safe_label)
                    if not col_lines:
                        col_lines = ['(no columns parsed)']
                    record_label = '{' + f"{t['name']}|" + '\\l'.join(col_lines) + '\\l' + '}'
                    dot_lines.append(f'  "{t["name"]}" [label="{record_label}"];')

                dot_lines.append('')

                # Relationship detection:
                edges = set()  # (child, parent, label, style, arrowhead)

                # 1) explicit table-level FKs if present in parsed metadata
                for t in tables:
                    parsed_fks = t.get('raw_props', {}).get('fks') or t.get('raw_props', {}).get('foreign_keys') or t.get('fks') or []
                    # parsed_fks could be list of dicts with 'references' & 'cols'
                    if isinstance(parsed_fks, list):
                        for fk in parsed_fks:
                            ref = fk.get('references') or fk.get('ref_table') or fk.get('referenced_table')
                            cols_label = ','.join(fk.get('cols', [])) if fk.get('cols') else ''
                            if ref:
                                ref_table = str(ref).split('.')[-1].strip().strip('[]`"')
                                parent = table_map.get(ref_table.lower())
                                if parent:
                                    edges.add((t['name'], parent, cols_label or '', 'solid', 'normal'))

                # 2) explicit inline references on column metadata (c['references'])
                for t in tables:
                    for c in t.get('columns', []):
                        ref = c.get('references')
                        if ref:
                            ref_table = str(ref).split('.')[-1].strip().strip('[]`"')
                            parent = table_map.get(ref_table.lower())
                            if parent:
                                edges.add((t['name'], parent, c.get('name') or '', 'dashed', 'normal'))

                # 3) Try to infer from inline column 'ref_cols' information within t['columns']
                for t in tables:
                    for c in t.get('columns', []):
                        ref_cols = c.get('ref_cols') or []
                        # sometimes ref_cols present without explicit references - try to map via heuristics
                        if ref_cols and not c.get('references'):
                            # attempt to find a parent table whose column names include any ref_cols value
                            for parent_lower, parent_display in table_map.items():
                                parent_table = next((pt for pt in tables if pt['name'] == parent_display), None)
                                if not parent_table:
                                    continue
                                parent_col_names = [pc['name'].lower() for pc in parent_table.get('columns', []) if pc.get('name')]
                                if any(rc.lower() in parent_col_names for rc in ref_cols):
                                    edges.add((t['name'], parent_display, c.get('name') or '', 'dashed', 'normal'))

                # 4) Heuristic by naming (only if no explicit FK already exists between the pair)
                for t in tables:
                    for c in t.get('columns', []):
                        if c.get('references'):
                            continue
                        hint = infer_referenced_table(c.get('name') or '')
                        if not hint:
                            continue
                        candidates = []
                        # exact singular match
                        if hint.lower() in table_map:
                            candidates.append(table_map[hint.lower()])
                        # plural s
                        plural_s = pluralize_s(hint).lower()
                        if plural_s in table_map:
                            candidates.append(table_map[plural_s])
                        # plural y -> ies
                        if hint.endswith('y'):
                            plural_ies = pluralize_ies(hint)
                            if plural_ies and plural_ies.lower() in table_map:
                                candidates.append(table_map[plural_ies.lower()])
                        # dedupe candidates and add as dotted edges if none exist yet
                        for cand in dict.fromkeys(candidates):
                            # avoid adding duplicate edges
                            if not any(e[0] == t['name'] and e[1] == cand for e in edges):
                                edges.add((t['name'], cand, c.get('name') or '', 'dotted', 'normal'))

                # 5) Render edges to DOT (sorted for determinism)
                for child, parent, lbl, style, arrow in sorted(edges, key=lambda x: (x[0], x[1], x[2])):
                    label_part = f' [label="{lbl}"]' if lbl else ''
                    # build attribute string
                    attr_parts = []
                    if lbl:
                        attr_parts.append(f'label="{lbl}"')
                    if style:
                        attr_parts.append(f'style="{style}"')
                    if arrow:
                        attr_parts.append(f'arrowhead="{arrow}"')
                    attr_str = ', '.join(attr_parts)
                    if attr_str:
                        dot_lines.append(f'  "{child}" -> "{parent}" [{attr_str}];')
                    else:
                        dot_lines.append(f'  "{child}" -> "{parent}";')

                dot_lines.append('}')
                dot = '\n'.join(dot_lines)
                return dot

        # Fallback: original LLM-based DOT generation (keeps existing behavior)
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
        # safe error fallback
        msg = str(e).replace("\n", " ").replace('"', "'")
        return f'digraph G {{ label="Error generating ER: {msg}" }}'



def parse_create_table_block(create_block: str) -> Dict[str, Any]:
    """
    Parse a single CREATE TABLE(...) SQL block and extract:
     - table_name
     - schema
     - columns: list of {name, sql_type, required, is_primary_key, references (dict or None), ref_cols}
     - table_level_foreign_keys: list of {columns: [...], ref_table: 'X', ref_schema: 'dbo', ref_columns: [...]}
    """

    result = {
        "table_name": None,
        "schema": "dbo",
        "columns": [],
        "table_level_foreign_keys": []
    }

    # Normalize whitespace for easier regex handling
    sb = create_block.strip()

    # Find table name + optional schema: supports forms like schema.table or [schema].[table] or table
    mname = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(?:(?:\[\s*([A-Za-z0-9_]+)\s*\])|([A-Za-z0-9_]+))?(?:\s*\.\s*)?(?:\[\s*([A-Za-z0-9_]+)\s*\]|([A-Za-z0-9_]+))',
        sb, re.IGNORECASE
    )

    if mname:
        # groups: maybe schema in group1 or group2; table in group3 or group4
        schema = mname.group(1) or mname.group(2)
        table = mname.group(3) or mname.group(4)
        if table:
            result['table_name'] = table
        if schema:
            result['schema'] = schema

    # Extract everything inside first pair of parentheses after CREATE TABLE
    body_match = re.search(r'CREATE\s+TABLE[^\(]*\((.*)\)\s*;?', sb, re.IGNORECASE | re.DOTALL)
    if not body_match:
        return result
    body = body_match.group(1).strip()

    # Split top-level comma separated pieces without breaking inside parentheses
    parts = []
    cur = ''
    depth = 0
    for ch in body:
        if ch == '(':
            depth += 1
        elif ch == ')':
            if depth > 0:
                depth -= 1
        if ch == ',' and depth == 0:
            if cur.strip():
                parts.append(cur.strip())
            cur = ''
        else:
            cur += ch
    if cur.strip():
        parts.append(cur.strip())

    # Parse parts: columns vs table-level constraints (PRIMARY KEY / FOREIGN KEY / CONSTRAINT)
    for part in parts:
        p = part.strip()
        if not p:
            continue

        # Table-level PRIMARY KEY or FOREIGN KEY (skip column parsing here)
        if re.match(r'^(CONSTRAINT|PRIMARY\s+KEY|FOREIGN\s+KEY|UNIQUE|CHECK)\b', p, re.IGNORECASE):
            # process in second pass for foreign keys / PKs
            continue

        # Column definition: [name] type ... (remainder may contain NOT NULL, PRIMARY KEY, REFERENCES)
        col_m = re.match(r'^(?:\[\s*([A-Za-z0-9_]+)\s*\]|([A-Za-z0-9_]+))\s+(.+)$', p, re.IGNORECASE | re.DOTALL)
        if not col_m:
            # fallback: store raw fragment as a column-like entry
            tokens = p.split()
            if tokens:
                result['columns'].append({
                    'name': tokens[0].strip('[]`"'),
                    'sql_type': ' '.join(tokens[1:]) if len(tokens) > 1 else '',
                    'required': 'NOT NULL' in p.upper(),
                    'is_primary_key': 'PRIMARY KEY' in p.upper(),
                    'references': None,
                    'ref_cols': []
                })
            continue

        col_name = col_m.group(1) or col_m.group(2)
        rest = col_m.group(3).strip()
        rest_upper = rest.upper()

        is_required = 'NOT NULL' in rest_upper
        is_pk = 'PRIMARY KEY' in rest_upper

        # inline REFERENCES?
        inline_ref = None
        inline_ref_cols = []
        ref_inline_m = re.search(
            r'REFERENCES\s+(?:\[\s*([A-Za-z0-9_]+)\s*\]\s*\.\s*)?(?:\[\s*([A-Za-z0-9_]+)\s*\]|([A-Za-z0-9_]+))\s*(?:\(\s*([^\)]+)\s*\))?',
            rest, re.IGNORECASE
        )
        if ref_inline_m:
            # ref_inline_m groups: maybe schema, table, alt_table, refcols
            ref_schema = ref_inline_m.group(1) or ''
            ref_table = ref_inline_m.group(2) or ref_inline_m.group(3) or ''
            refcols_raw = ref_inline_m.group(4) or ''
            inline_ref = {
                'schema': ref_schema or result['schema'],
                'table': ref_table,
                'column': None
            }
            if refcols_raw:
                inline_ref_cols = [c.strip().strip('[]`"') for c in refcols_raw.split(',')]

        result['columns'].append({
            'name': col_name,
            'sql_type': re.split(r'\s+', rest, maxsplit=1)[0] if rest else '',
            'required': is_required,
            'is_primary_key': is_pk,
            'references': inline_ref,
            'ref_cols': inline_ref_cols
        })

    # Second pass: find table-level FOREIGN KEY / PRIMARY KEY constraints and attach to columns
    # e.g. FOREIGN KEY (emp_no) REFERENCES employees (emp_no)
    for fk_m in re.finditer(
        r'(?:CONSTRAINT\s+\[?[A-Za-z0-9_]+\]?\s+)?FOREIGN\s+KEY\s*\(\s*([^\)]+)\s*\)\s*REFERENCES\s+(?:\[\s*([A-Za-z0-9_]+)\s*\]\s*\.\s*)?(?:\[\s*([A-Za-z0-9_]+)\s*\]|([A-Za-z0-9_]+))\s*\(\s*([^\)]+)\s*\)',
        body, re.IGNORECASE):
        local_cols_raw = fk_m.group(1)
        ref_schema = fk_m.group(2) or ''
        ref_table = fk_m.group(3) or fk_m.group(4) or ''
        ref_cols_raw = fk_m.group(5) or ''

        local_cols = [c.strip().strip('[]`"') for c in re.split(r',\s*', local_cols_raw) if c.strip()]
        ref_cols = [c.strip().strip('[]`"') for c in re.split(r',\s*', ref_cols_raw) if c.strip()]

        # store table-level fk record
        result['table_level_foreign_keys'].append({
            'columns': local_cols,
            'ref_table': ref_table,
            'ref_schema': ref_schema or result['schema'],
            'ref_columns': ref_cols
        })

        # attach references to individual columns where names match
        for i, lc in enumerate(local_cols):
            for col in result['columns']:
                if col['name'].lower() == lc.lower():
                    col['references'] = {
                        'schema': ref_schema or result['schema'],
                        'table': ref_table,
                        'column': ref_cols[i] if i < len(ref_cols) else None
                    }

    # Also capture table-level PRIMARY KEY (if any)
    pk_m = re.search(r'PRIMARY\s+KEY\s*\(\s*([^\)]+)\s*\)', body, re.IGNORECASE)
    if pk_m:
        pk_cols = [c.strip().strip('[]`"') for c in re.split(r',\s*', pk_m.group(1)) if c.strip()]
        for col in result['columns']:
            if col['name'] in pk_cols:
                col['is_primary_key'] = True

    return result


