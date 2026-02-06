import asyncio
import logging
import hashlib
import time
from typing import List, Dict, Any, Optional

# --- IMPORTACIONES ---
from src.services.learning.domain.entities import GeneratedQuestion, QuestionType, NumericalValidation

# Importamos los modelos Pydantic CORRECTOS (V5.0)
from src.services.learning.api.schemas import StudentAnswer, QuestionFeedbackDetail, ExamResultResponse
from src.services.ai.service import AIService

logger = logging.getLogger(__name__)

class GraderEngine:
    # Configuración
    MAX_SCORE = 100.0
    XP_MULTIPLIER = 15
    XP_DIVISOR = 10
    TOLERANCE_EPSILON = 1e-9
    AI_CONCURRENCY_LIMIT = 50 
    CACHE_TTL = 86400 

    def __init__(self, ai_service: AIService, cache_service=None):
        self.ai_service = ai_service
        self.cache = cache_service
        self._ai_semaphore = asyncio.Semaphore(self.AI_CONCURRENCY_LIMIT)

    async def grade_exam(self, exam_questions: List[GeneratedQuestion], answers: List[StudentAnswer]) -> Dict[str, Any]:
        """Orquestador principal."""
        start_time = time.time()
        q_map = {q.id: q for q in exam_questions}
        max_possible = len(exam_questions) * self.MAX_SCORE
        
        tasks = []
        for ans in answers:
            question = q_map.get(ans.question_id)
            if question:
                tasks.append(self._process_single_answer(question, ans))
        
        # Ejecutamos en paralelo y obtenemos objetos QuestionFeedbackDetail
        results: List[QuestionFeedbackDetail] = await asyncio.gather(*tasks)

        # Totales
        total_score = sum(r.score for r in results)
        
        # Cálculo de porcentaje seguro (evitar división por cero)
        final_percentage = (total_score / max_possible * 100) if max_possible > 0 else 0.0
        
        # XP Gamification
        xp = int(final_percentage / self.XP_DIVISOR) * self.XP_MULTIPLIER

        meta = {
            "execution_time_ms": int((time.time() - start_time) * 1000),
            "ai_usage_count": sum(1 for r in results if r.source == 'ai'),
            "cache_hit_count": sum(1 for r in results if r.source == 'cache'),
            "computed_count": sum(1 for r in results if r.source == 'computed')
        }

        # --- MEJORA CRÍTICA ---
        # Convertimos la lista a un diccionario {question_id: detalle}
        details_map = {r.question_id: r.model_dump() for r in results}

        return {
            "total_score": round(final_percentage, 2),
            "xp_earned": xp,
            "details": details_map, # <-- Dict, no List
            "meta": meta
        }

    async def _process_single_answer(self, question: GeneratedQuestion, answer: StudentAnswer) -> QuestionFeedbackDetail:
        """Pipeline: Fast Math -> Cache -> AI -> Fallback"""
        
        # 1. Corrección Matemática Rápida
        fast_result = self._grade_fast_math(question, answer)

        # 2. Decisión: ¿Necesitamos IA?
        needs_ai = (
            fast_result.score < self.MAX_SCORE 
            and answer.text_content 
            and len(str(answer.text_content).strip()) > 5
        )

        if not needs_ai:
            return fast_result

        # 3. Corrección Inteligente (AI Resilient)
        return await self._grade_with_ai_resilient(question, answer, fast_result)

    async def _grade_with_ai_resilient(self, question: GeneratedQuestion, answer: StudentAnswer, fallback: QuestionFeedbackDetail) -> QuestionFeedbackDetail:
        # Cache Check
        content_hash = hashlib.md5(f"{answer.text_content}".encode()).hexdigest()
        cache_key = f"grade:v5:{question.id}:{content_hash}" # Incrementamos versión cache

        if self.cache:
            try:
                cached = await self.cache.get(cache_key)
                if cached:
                    return QuestionFeedbackDetail(**cached)
            except Exception:
                pass

        # AI Call
        async with self._ai_semaphore:
            try:
                # Preparamos el valor correcto para mostrar
                correct_display = fallback.correct_solution or str(question.validation_rules.correct_value)
                
                # Llamada al servicio de IA
                evaluation = await self.ai_service.evaluate_reasoning(
                    question_text=question.statement_latex,
                    correct_value=correct_display,
                    student_value=str(answer.numeric_value or "N/A"),
                    student_procedure=answer.text_content or ""
                )
                
                # Extracción segura de la respuesta de la IA
                new_score = float(evaluation.get('adjusted_score_percentage', 0))
                
                # Política de Benevolencia: Nos quedamos con la nota más alta (IA vs Matemáticas)
                final_score = max(new_score, fallback.score)
                
                feedback_ai = evaluation.get('feedback_text', 'Análisis IA completado.')

                result = QuestionFeedbackDetail(
                    question_id=question.id,
                    score=final_score,
                    status="partial" if final_score < 100 else "correct",
                    feedback_text=feedback_ai,
                    correct_solution=correct_display,
                    source="ai"
                )

                if self.cache:
                    asyncio.create_task(self.cache.set(cache_key, result.model_dump(), self.CACHE_TTL))

                return result

            except Exception as e:
                logger.error(f"AI Grader fail: {e}")
                # Creamos una copia nueva explícita para evitar mutaciones ilegales
                return QuestionFeedbackDetail(
                    question_id=fallback.question_id,
                    score=fallback.score,
                    status=fallback.status,
                    feedback_text=fallback.feedback_text + " (Revisión IA no disponible)",
                    correct_solution=fallback.correct_solution,
                    source="fallback"
                )

    def _grade_fast_math(self, question: GeneratedQuestion, answer: StudentAnswer) -> QuestionFeedbackDetail:
        """Lógica matemática pura (Deterministic)"""
        rule = question.validation_rules
        correct_display = f"{rule.correct_value}"
        
        # Helper interno para crear respuesta rápida
        def make_resp(score, status, txt):
            return QuestionFeedbackDetail(
                question_id=question.id,
                score=float(score),
                status=status,
                feedback_text=txt,
                correct_solution=correct_display,
                source="computed"
            )

        # 1. Validación Numérica
        if question.question_type == QuestionType.NUMERIC_INPUT and isinstance(rule, NumericalValidation):
            if answer.numeric_value is None:
                return make_resp(0, "incorrect", "Sin respuesta numérica")
            
            try:
                user_val = float(answer.numeric_value)
                correct_val = rule.correct_value
                tolerance = rule.tolerance_percentage / 100.0
                
                # Check valor (con tolerancia relativa)
                if correct_val == 0: 
                    is_close = abs(user_val) < self.TOLERANCE_EPSILON
                else: 
                    is_close = abs(user_val - correct_val) <= abs(correct_val * tolerance)
                
                if not is_close:
                    return make_resp(0, "incorrect", "El valor numérico no coincide con la solución.")
                
                # Check Unidades (Legacy support: answer.unit puede ser None)
                unit_penalty = 0.0
                feedback = "¡Resultado exacto!"
                
                if rule.allowed_units and answer.unit:
                    user_u = str(answer.unit).strip().lower()
                    allowed_u = [u.lower() for u in rule.allowed_units]
                    if user_u not in allowed_u:
                        unit_penalty = 50.0
                        feedback = f"Valor correcto, pero unidad incorrecta (Esperada: {rule.allowed_units[0]})."
                
                final_score = max(0.0, self.MAX_SCORE - unit_penalty)
                status = "correct" if final_score == 100 else "partial"
                
                return make_resp(final_score, status, feedback)
                
            except ValueError:
                return make_resp(0, "incorrect", "Formato numérico inválido")

        return make_resp(0, "pending", "Tipo de pregunta no soportado por Grader V5")