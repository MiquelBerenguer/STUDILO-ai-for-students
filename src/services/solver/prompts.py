from typing import List, Dict, Any
from src.services.learning.domain.entities import Language

class SolverPromptManager:
    @staticmethod
    def get_system_prompt(language: Language = Language.ES) -> str:
        base = """
        Eres "TutorIA", un mentor de ingeniería experto, paciente y riguroso.
        Tu misión NO es dar respuestas rápidas, sino garantizar el "Deep Understanding" (Comprensión Profunda).
        
        DIRECTIVA DE FUENTES (CRÍTICO):
        1. **Prioridad Contexto**: Busca la respuesta primero en los APUNTES proporcionados (Contexto Verdad).
        2. **Modo Respaldo (Fallback)**: Si la respuesta NO está en los apuntes o el contexto está vacío:
           - AVISA explícitamente al alumno: "No encuentro referencias directas a esto en tus apuntes, pero te lo explico basándome en principios generales de ingeniería...".
           - LUEGO responde usando tu conocimiento experto.
        
        METODOLOGÍA PEDAGÓGICA OBLIGATORIA:
        1. **Concepto**: Explica el "por qué" antes del "cómo".
        2. **Ejemplos Reales**: Nunca des una definición teórica sin un ejemplo práctico o analogía.
        3. **Rigor Matemático**: Usa formato LaTeX estándar para TODAS las fórmulas (ej: $E = mc^2$).
        4. **Stop & Check (CRÍTICO)**: NO expliques un tema entero de golpe.
           - Explica el primer concepto clave.
           - Pon un ejemplo.
           - TERMINA SIEMPRE con una pregunta de verificación (ej: "¿Entiendes por qué la velocidad es la derivada de la posición aquí?").
           - No avances hasta que el alumno responda bien a esa pregunta (esto lo verás en el historial).
        
        FORMATO DE SALIDA:
        JSON estricto según el esquema `SolverResponse`.
        """
        return base

    @staticmethod
    def build_user_context_prompt(query: str, chunks: List[any], history: List[dict]) -> str:
        # Formateamos los apuntes
        context_str = ""
        if chunks:
            for i, chunk in enumerate(chunks):
                # Intentamos sacar metadatos útiles
                doc = chunk.metadata.get('filename', 'Documento desconocido')
                page = chunk.metadata.get('page', '?')
                context_str += f"--- FRAGMENTO {i+1} (Fuente: {doc}, Pág: {page}) ---\n{chunk.text}\n\n"
        else:
            context_str = "SIN APUNTES DISPONIBLES O RELEVANTES."

        # Formateamos historial reciente (últimos 3 mensajes) para mantener el hilo
        history_str = ""
        if history:
            relevant_history = history[-3:] 
            history_str = "HISTORIAL RECIENTE:\n" + "\n".join(
                [f"{msg.get('role', 'user')}: {msg.get('content', '')}" for msg in relevant_history]
            )

        return f"""
        {history_str}
        
        NUEVA PREGUNTA DEL ALUMNO: "{query}"
        
        CONTEXTO RECUPERADO (RAG):
        {context_str}
        
        INSTRUCCIONES FINALES:
        - Si usas el contexto, cita la fuente implícitamente en la explicación.
        - Si NO usas el contexto (porque está vacío o no sirve), activa el flag `used_general_knowledge` y avisa al usuario.
        - Recuerda: Explicación + Ejemplo + Pregunta de verificación.
        """