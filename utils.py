# utils.py - COMPLETE FILE WITH TOKEN-AWARE SMART CHUNKING
from pathlib import Path
import re
from typing import List

CODE_EXTS = {".cs", ".ts", ".tsx", ".sql", ".cshtml", ".html", ".config", ".js"}

def is_code_file(path: str) -> bool:
    return Path(path).suffix.lower() in CODE_EXTS


def read_text_safe(p: str) -> str:
    try:
        with open(p, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    except Exception:
        return ""


def sha1(text: str) -> str:
    import hashlib
    return hashlib.sha1(text.encode("utf-8", errors="ignore")).hexdigest()


# ============================================================
# ✅ NEW: TOKEN ESTIMATION
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


# ============================================================
# ✅ ENHANCED: TOKEN-AWARE SMART CHUNKING
# ============================================================

def sliding_window(text: str, max_chars: int, overlap: int) -> List[str]:
    """
    Token-aware smart chunking that respects code structure boundaries.
    
    Target: ~800 tokens per chunk (leaves ~7400 for system prompts + metadata)
    Context limit: 8192 tokens total for gpt-3.5-turbo
    """
    n = len(text)
    if n == 0:
        return []
    
    # Check if entire text fits within token limit
    total_tokens = estimate_tokens(text)
    TARGET_TOKENS = 500  # ⚠️ CHANGED FROM 1500
    
    if total_tokens <= TARGET_TOKENS:
        return [text]
    
    # Try smart chunking first
    smart_chunks = _smart_chunk_with_token_limit(text, max_chars, overlap, TARGET_TOKENS)
    if smart_chunks:
        return smart_chunks
    
    # Fallback to token-aware character chunking
    return _token_aware_character_chunk(text, TARGET_TOKENS, overlap)


def _smart_chunk_with_token_limit(text: str, max_chars: int, overlap: int, target_tokens: int) -> List[str]:
    """
    Chunk code by respecting logical boundaries AND token limits
    """
    chunks = []
    
    # Detect file type
    file_type = _detect_file_type(text)
    
    if file_type in ['csharp', 'typescript', 'javascript']:
        chunks = _chunk_by_braces_with_tokens(text, max_chars, overlap, target_tokens)
    elif file_type == 'sql':
        chunks = _chunk_by_sql_blocks_with_tokens(text, max_chars, overlap, target_tokens)
    else:
        chunks = _chunk_by_paragraphs_with_tokens(text, max_chars, overlap, target_tokens)
    
    return chunks


def _detect_file_type(text: str) -> str:
    """Quick heuristic to detect file type"""
    text_lower = text.lower()
    
    if 'public class' in text_lower or 'namespace' in text_lower or 'using system' in text_lower:
        return 'csharp'
    elif 'export class' in text_lower or 'import {' in text_lower or '@component' in text_lower:
        return 'typescript'
    elif 'function(' in text_lower or 'const ' in text_lower or 'var ' in text_lower:
        return 'javascript'
    elif 'create procedure' in text_lower or 'begin' in text_lower and 'end' in text_lower:
        return 'sql'
    else:
        return 'unknown'


def _chunk_by_braces_with_tokens(text: str, max_chars: int, overlap: int, target_tokens: int) -> List[str]:
    """
    Chunk C#/TypeScript by method/class boundaries with token awareness
    """
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_tokens = 0
    brace_depth = 0
    method_start_depth = None
    
    for line in lines:
        line_tokens = estimate_tokens(line)
        
        # Track brace depth
        brace_depth += line.count('{') - line.count('}')
        
        # Detect method/class start
        if re.search(r'(public|private|protected|export|async)\s+(class|interface|function|async|[\w<>]+)\s+\w+\s*[({]', line):
            method_start_depth = brace_depth
        
        # Check if we should start new chunk
        if current_tokens + line_tokens > target_tokens:
            # Try to break at method boundary
            if brace_depth == 0 or (method_start_depth is not None and brace_depth < method_start_depth):
                if current_chunk:
                    chunk_text = '\n'.join(current_chunk)
                    
                    # If chunk is still too large, sub-divide it
                    if estimate_tokens(chunk_text) > target_tokens * 1.5:
                        sub_chunks = _force_split_large_chunk(chunk_text, target_tokens, overlap)
                        chunks.extend(sub_chunks)
                    else:
                        chunks.append(chunk_text)
                    
                    # Add overlap
                    overlap_lines = _get_overlap_lines(current_chunk, overlap)
                    current_chunk = overlap_lines
                    current_tokens = sum(estimate_tokens(l) for l in overlap_lines)
        
        current_chunk.append(line)
        current_tokens += line_tokens
        
        # Force break if chunk is getting too large (2x target)
        if current_tokens > target_tokens * 2:
            if current_chunk:
                chunk_text = '\n'.join(current_chunk)
                sub_chunks = _force_split_large_chunk(chunk_text, target_tokens, overlap)
                chunks.extend(sub_chunks)
                current_chunk = []
                current_tokens = 0
    
    # Add final chunk
    if current_chunk:
        chunk_text = '\n'.join(current_chunk)
        if estimate_tokens(chunk_text) > target_tokens * 1.5:
            sub_chunks = _force_split_large_chunk(chunk_text, target_tokens, overlap)
            chunks.extend(sub_chunks)
        else:
            chunks.append(chunk_text)
    
    return chunks if chunks else None


def _chunk_by_sql_blocks_with_tokens(text: str, max_chars: int, overlap: int, target_tokens: int) -> List[str]:
    """
    Chunk SQL by procedure/function boundaries with token awareness
    """
    chunks = []
    
    # Split by stored procedures/functions
    proc_pattern = r'(CREATE\s+(?:PROCEDURE|FUNCTION|TRIGGER|VIEW)\s+.*?(?=CREATE\s+(?:PROCEDURE|FUNCTION|TRIGGER|VIEW)|$))'
    procedures = re.findall(proc_pattern, text, re.IGNORECASE | re.DOTALL)
    
    if procedures:
        for proc in procedures:
            proc_tokens = estimate_tokens(proc)
            
            if proc_tokens <= target_tokens:
                chunks.append(proc)
            else:
                # Large procedure - split by BEGIN/END blocks
                sub_chunks = _split_large_sql_with_tokens(proc, target_tokens, overlap)
                chunks.extend(sub_chunks)
    else:
        # No procedures - split by statement boundaries
        return _chunk_by_sql_statements_with_tokens(text, target_tokens, overlap)
    
    return chunks if chunks else None


def _split_large_sql_with_tokens(proc: str, target_tokens: int, overlap: int) -> List[str]:
    """Split large SQL procedure by BEGIN/END blocks with token awareness"""
    chunks = []
    lines = proc.split('\n')
    current_chunk = []
    current_tokens = 0
    depth = 0
    
    for line in lines:
        line_tokens = estimate_tokens(line)
        
        # Track BEGIN/END depth
        if re.search(r'\bBEGIN\b', line, re.IGNORECASE):
            depth += 1
        if re.search(r'\bEND\b', line, re.IGNORECASE):
            depth -= 1
        
        if current_tokens + line_tokens > target_tokens and depth == 0:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                overlap_lines = _get_overlap_lines(current_chunk, overlap)
                current_chunk = overlap_lines
                current_tokens = sum(estimate_tokens(l) for l in overlap_lines)
        
        current_chunk.append(line)
        current_tokens += line_tokens
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def _chunk_by_sql_statements_with_tokens(text: str, target_tokens: int, overlap: int) -> List[str]:
    """Split SQL by statement boundaries with token awareness"""
    statements = text.split(';')
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for stmt in statements:
        stmt = stmt.strip()
        if not stmt:
            continue
        
        stmt_tokens = estimate_tokens(stmt)
        
        if current_tokens + stmt_tokens > target_tokens:
            if current_chunk:
                chunks.append(';\n'.join(current_chunk) + ';')
                current_chunk = []
                current_tokens = 0
        
        current_chunk.append(stmt)
        current_tokens += stmt_tokens
    
    if current_chunk:
        chunks.append(';\n'.join(current_chunk) + ';')
    
    return chunks


def _chunk_by_paragraphs_with_tokens(text: str, max_chars: int, overlap: int, target_tokens: int) -> List[str]:
    """Chunk text files by paragraphs with token awareness"""
    paragraphs = re.split(r'\n\s*\n', text)
    chunks = []
    current_chunk = []
    current_tokens = 0
    
    for para in paragraphs:
        para_tokens = estimate_tokens(para)
        
        if current_tokens + para_tokens > target_tokens:
            if current_chunk:
                chunks.append('\n\n'.join(current_chunk))
                current_chunk = []
                current_tokens = 0
        
        current_chunk.append(para)
        current_tokens += para_tokens
    
    if current_chunk:
        chunks.append('\n\n'.join(current_chunk))
    
    return chunks


def _force_split_large_chunk(text: str, target_tokens: int, overlap: int) -> List[str]:
    """
    Force split a chunk that's too large, even if it breaks code structure.
    Used as last resort for very large methods/functions.
    """
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_tokens = 0
    
    for line in lines:
        line_tokens = estimate_tokens(line)
        
        if current_tokens + line_tokens > target_tokens:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                # Add overlap
                overlap_lines = _get_overlap_lines(current_chunk, overlap)
                current_chunk = overlap_lines
                current_tokens = sum(estimate_tokens(l) for l in overlap_lines)
        
        current_chunk.append(line)
        current_tokens += line_tokens
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks


def _get_overlap_lines(lines: List[str], overlap_chars: int) -> List[str]:
    """Get last few lines that fit in overlap size"""
    overlap_lines = []
    overlap_size = 0
    
    for line in reversed(lines):
        line_size = len(line) + 1
        if overlap_size + line_size > overlap_chars:
            break
        overlap_lines.insert(0, line)
        overlap_size += line_size
    
    return overlap_lines


def _token_aware_character_chunk(text: str, target_tokens: int, overlap: int) -> List[str]:
    """
    Fallback: Character-based chunking but with token awareness
    """
    chunks = []
    lines = text.split('\n')
    current_chunk = []
    current_tokens = 0
    
    for line in lines:
        line_tokens = estimate_tokens(line)
        
        if current_tokens + line_tokens > target_tokens:
            if current_chunk:
                chunks.append('\n'.join(current_chunk))
                overlap_lines = _get_overlap_lines(current_chunk, overlap)
                current_chunk = overlap_lines
                current_tokens = sum(estimate_tokens(l) for l in overlap_lines)
        
        current_chunk.append(line)
        current_tokens += line_tokens
    
    if current_chunk:
        chunks.append('\n'.join(current_chunk))
    
    return chunks

def validate_chunk_size(chunk: str, max_tokens: int = 800) -> bool:
    """Validate that a chunk is within safe token limits"""
    tokens = estimate_tokens(chunk)
    if tokens > max_tokens:
        print(f"⚠️ Warning: Chunk has {tokens} tokens (max: {max_tokens})")
        return False
    return True