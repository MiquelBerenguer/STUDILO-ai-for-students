import logging
import json
import ast
import re
from datetime import datetime
from jinja2 import Template
from weasyprint import HTML, CSS
from src.services.learning.domain.entities import Exam

logger = logging.getLogger(__name__)

class PDFRenderer:
    def __init__(self):
        # ESTILO ACADÉMICO (Inspirado en AM2_2324-2_E2.pdf)
        self.css_style = """
            @page { 
                size: A4; 
                margin: 2.5cm 2cm; /* Márgenes generosos como en el ejemplo */
                @bottom-center {
                    content: counter(page);
                    font-family: 'Times New Roman', serif;
                    font-size: 10pt;
                }
            }
            
            body { 
                font-family: 'Times New Roman', 'Georgia', serif; /* Toque académico */
                line-height: 1.4; 
                color: #000; 
                font-size: 11pt;
            }
            
            /* CABECERA */
            .exam-header {
                font-family: 'Arial', 'Helvetica', sans-serif;
                margin-bottom: 30px;
                border-bottom: 1px solid #000;
                padding-bottom: 10px;
                display: flex;
                justify-content: space-between;
                align-items: flex-end;
            }
            
            .course-title {
                font-size: 14pt;
                font-weight: bold;
                text-transform: uppercase;
            }
            
            .exam-info {
                text-align: right;
                font-size: 10pt;
            }

            /* INSTRUCCIONES */
            .instructions {
                font-style: italic;
                margin-bottom: 30px;
                font-size: 10pt;
                padding: 10px;
                border: 1px solid #ddd;
                background-color: #f9f9f9;
            }

            /* PREGUNTAS */
            .question-container {
                margin-bottom: 25px;
                break-inside: avoid; /* Evita que una pregunta se corte entre páginas */
            }
            
            .q-num {
                font-weight: bold;
                float: left;
                margin-right: 10px;
            }
            
            .q-text {
                margin-left: 25px;
                text-align: justify;
                margin-bottom: 15px;
            }

            /* ZONAS DE RESPUESTA */
            .work-area {
                margin-left: 25px;
                margin-top: 10px;
                min-height: 100px;
                border: 1px solid #e0e0e0; /* Marco muy sutil para escribir */
                padding: 10px;
            }
            
            .code-area {
                font-family: 'Courier New', monospace;
                background: #f4f4f4;
                padding: 10px;
                border-left: 4px solid #333;
                font-size: 10pt;
                margin-left: 25px;
            }

            /* OPCIONES TEST */
            .options-list {
                list-style: none;
                padding-left: 25px;
            }
            .option-item {
                margin-bottom: 5px;
            }
            .checkbox {
                display: inline-block;
                width: 12px;
                height: 12px;
                border: 1px solid #000;
                margin-right: 8px;
            }
            
            .meta-tag {
                font-size: 8pt; 
                color: #666; 
                font-family: sans-serif;
                margin-left: 5px;
            }
        """

        self.html_template = """
        <!DOCTYPE html>
        <html>
        <head><style>{{ css }}</style></head>
        <body>
            <div class="exam-header">
                <div class="course-title">
                    {{ exam.config.course_id | replace('_', ' ') | upper }}
                </div>
                <div class="exam-info">
                    <strong>Examen Generado</strong><br>
                    {{ date }}<br>
                    ID: {{ exam.id.split('-')[0] }}
                </div>
            </div>

            <div class="instructions">
                <strong>Instrucciones:</strong>
                <ul>
                    <li>Responda claramente a cada ejercicio.</li>
                    <li>Justifique todas las respuestas numéricas.</li>
                    <li>Utilice el espacio provisto o adjunte hojas adicionales si es necesario.</li>
                </ul>
            </div>

            {% for q in exam.questions %}
            <div class="question-container">
                <div class="q-num">{{ loop.index }}.</div>
                
                <div class="q-text">
                    {{ clean_latex(q.statement_latex) | replace('\n', '<br>') }}
                    <span class="meta-tag">({{ q.difficulty.value | default('general') }})</span>
                </div>

                {% if q.question_type.value == 'multiple_choice' %}
                    <ul class="options-list">
                    {% if q.validation_rules and q.validation_rules.options %}
                        {% for opt in q.validation_rules.options %}
                            <li class="option-item"><span class="checkbox"></span> {{ opt }}</li>
                        {% endfor %}
                    {% else %}
                        <li class="option-item"><span class="checkbox"></span> a) ___________________</li>
                        <li class="option-item"><span class="checkbox"></span> b) ___________________</li>
                        <li class="option-item"><span class="checkbox"></span> c) ___________________</li>
                        <li class="option-item"><span class="checkbox"></span> d) ___________________</li>
                    {% endif %}
                    </ul>

                {% elif q.question_type.value == 'code_editor' %}
                    <div class="code-area">
                        <strong>def solucion(datos):</strong><br>
                        &nbsp;&nbsp;&nbsp;&nbsp;# Escriba su algoritmo aquí<br>
                        &nbsp;&nbsp;&nbsp;&nbsp;pass
                    </div>
                    <div class="work-area" style="height: 80px; border:none; border-bottom:1px dashed #ccc;">
                        <small style="color:#666">Espacio para traza o pseudocódigo</small>
                    </div>

                {% elif q.question_type.value == 'numeric_input' %}
                    <div class="work-area" style="height: 150px;">
                        {% if q.validation_rules and q.validation_rules.allowed_units %}
                            <div style="position: absolute; right: 40px; margin-top: 120px;">
                                <strong>Resultado:</strong> _____________ [{{ q.validation_rules.allowed_units | join(', ') }}]
                            </div>
                        {% endif %}
                    </div>

                {% else %}
                    <div class="work-area" style="height: 150px;"></div>
                {% endif %}
            </div>
            {% endfor %}
        </body>
        </html>
        """

    def _clean_latex_content(self, raw_content: str) -> str:
        """
        🧹 LIMPIEZA PROFUNDA DE STRINGS
        Detecta si el string es un diccionario Python/JSON stringificado y extrae el texto real.
        """
        if not raw_content:
            return "Pregunta sin contenido."
            
        text_to_process = str(raw_content).strip()
        
        # 1. Detectar si parece un diccionario {'key': 'val'}
        if text_to_process.startswith("{") and "statement" in text_to_process:
            try:
                # Intento 1: JSON estándar
                data = json.loads(text_to_process)
                return self._extract_from_dict(data)
            except json.JSONDecodeError:
                try:
                    # Intento 2: Python Literal (para cuando hay comillas simples ' ' en vez de " ")
                    data = ast.literal_eval(text_to_process)
                    if isinstance(data, dict):
                        return self._extract_from_dict(data)
                except Exception:
                    pass # Si falla, asumimos que es texto plano con llaves
        
        # 2. Limpieza Cosmética de LaTeX para PDF plano
        # Quitamos delimitadores molestos para lectura humana si WeasyPrint no los renderiza
        text_to_process = text_to_process.replace(r"\[", "").replace(r"\]", "")
        # Opcional: Si quieres mantener $ para fórmulas inline, déjalo.
        
        return text_to_process

    def _extract_from_dict(self, data: dict) -> str:
        """Helper para sacar el texto de un dict con varias posibles claves"""
        return (
            data.get("statement_latex") or 
            data.get("statement") or 
            data.get("question") or 
            data.get("content") or 
            "Error extrayendo enunciado."
        )

    def render_to_bytes(self, exam: Exam) -> bytes:
        try:
            logger.info(f"📄 Renderizando PDF Estilo Académico para: {exam.id}")
            template = Template(self.html_template)
            
            html_content = template.render(
                css=self.css_style,
                exam=exam,
                date=datetime.now().strftime("%d/%m/%Y"),
                clean_latex=self._clean_latex_content # Pasamos la función de limpieza
            )
            
            return HTML(string=html_content).write_pdf()

        except Exception as e:
            logger.error(f"❌ Error Renderizando PDF: {e}")
            raise e