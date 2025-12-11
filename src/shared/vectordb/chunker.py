import re
from typing import List

class EngineeringChunker:
    """
    Divisor de texto consciente de LaTeX y Estructura.
    Garantiza que ningún chunk termine con un bloque $$ abierto.
    """
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap

    def validate_math_integrity(self, text: str) -> bool:
        """Devuelve True si los bloques matemáticos están balanceados (pares)."""
        return text.count("$$") % 2 == 0

    def split_text(self, text: str) -> List[str]:
        text = text.replace('\r\n', '\n')
        paragraphs = re.split(r'\n\s*\n', text)
        
        chunks = []
        current_chunk = []
        current_length = 0
        
        for para in paragraphs:
            para = para.strip()
            if not para: continue
            
            para_len = len(para)
            
            if current_length + para_len > self.chunk_size:
                temp_text = "\n\n".join(current_chunk)
                
                if self.validate_math_integrity(temp_text):
                    chunks.append(temp_text)
                    overlap_text = temp_text[-self.chunk_overlap:] if self.chunk_overlap < len(temp_text) else temp_text
                    current_chunk = [overlap_text, para]
                    current_length = len(overlap_text) + para_len
                else:
                    # FORZAR EXTENSIÓN: Estamos dentro de una ecuación
                    current_chunk.append(para)
                    current_length += para_len
            else:
                current_chunk.append(para)
                current_length += para_len

        if current_chunk:
            chunks.append("\n\n".join(current_chunk))
            
        return chunks