from typing import List
from src.services.learning.domain.entities import (
    ExamConfig, Exam, GeneratedQuestion, ExamDifficulty
)
from src.services.learning.logic.content_selector import ContentSelector
from src.services.learning.logic.style_selector import StyleSelector
from src.services.learning.logic.blueprint import ExamBlueprintBuilder
from src.services.ai.client import AIService
from datetime import datetime

class ExamGenerator:
    def __init__(
        self,
        content_selector: ContentSelector,
        style_selector: StyleSelector,
        ai_service: AIService
    ):
        self.content_selector = content_selector
        self.style_selector = style_selector
        self.ai_service = ai_service
        self.blueprint_builder = ExamBlueprintBuilder()

    async def generate_exam(self, config: ExamConfig) -> Exam:
        print(f"--- 🏗️  PLANIFICANDO EXAMEN: {config.course_id} ---")

        # 1. OBTENER TEMAS DISPONIBLES
        topics = await self.content_selector.get_available_topics(config)
        
        # 2. CREAR EL PLANO (BLUEPRINT)
        # Esto decide: "Pregunta 1: Fácil, Tema A. Pregunta 10: Difícil, Tema B".
        exam_slots = self.blueprint_builder.create_blueprint(config, topics)
        
        generated_questions = []

        # 3. CONSTRUCCIÓN (Iterar sobre el plano)
        for slot in exam_slots:
            print(f"Generando Pregunta {slot.slot_index}/{len(exam_slots)}... (Diff: {slot.difficulty.value})")
            
            # A. Contexto (RAG)
            chunks = await self.content_selector.fetch_context_for_slot(
                config.course_id, 
                slot.topic_id
            )
            
            # B. Estilo (Patrones)
            # Buscamos un patrón que encaje con la Dificultad y Tipo Cognitivo del slot
            pattern = await self.style_selector.select_best_pattern(
                course_id=config.course_id,
                domain="engineering", 
                cognitive_needed=slot.cognitive_target,
                difficulty=slot.difficulty
            )
            
            # C. Prompting
            prompt = self._build_prompt(slot, chunks, pattern)
            
            # D. Generación AI
            q_data = await self.ai_service.generate_json(
                prompt=prompt,
                schema={}, # Schema implícito en el prompt por ahora
                model="smart" 
            )
            
            # E. Guardado
            generated_questions.append(
                GeneratedQuestion(
                    question_text=q_data["question_text"],
                    options=q_data.get("options"),
                    correct_answer=q_data["correct_answer"],
                    explanation=f"[Valor: {slot.points} pts] " + q_data["explanation"],
                    source_chunk_id=chunks[0] if chunks else "general_knowledge",
                    used_pattern_id=pattern.id if pattern else "default_logic"
                )
            )

        # 4. ENTREGA FINAL
        return Exam(
            id="exam_" + datetime.now().strftime("%Y%m%d%H%M"),
            course_id=config.course_id,
            student_id=config.student_id,
            created_at=datetime.now(),
            questions=generated_questions,
            config_snapshot=config,
            ai_model_used="gpt-4-turbo-blueprint"
        )

    def _build_prompt(self, slot, chunks, pattern):
        """Construye el prompt específico para este Slot."""
        rag_text = "\n".join([f"- {c}" for c in chunks])
        
        style_instr = ""
        if pattern:
            style_instr = f"""
            IMPERATIVO DE ESTILO (Imita esta lógica de examen anterior):
            Arquetipo: {pattern.reasoning_recipe}
            Ejemplo Original: "{pattern.original_question}"
            """
        
        return f"""
        Genera la Pregunta #{slot.slot_index} de un examen.
        Tema: {slot.topic_id}
        Dificultad: {slot.difficulty.value.upper()}
        Valor: {slot.points} puntos.
        
        CONTEXTO TEÓRICO:
        {rag_text}
        
        {style_instr}
        
        FORMATO JSON ESPERADO:
        {{
            "question_text": "...",
            "options": ["A", "B", "C", "D"] (solo si aplica),
            "correct_answer": "...",
            "explanation": "..."
        }}
        """