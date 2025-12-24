import logging
from jinja2 import Template
from weasyprint import HTML, CSS  # Import directo, sin miedo

from src.services.learning.domain.entities import Exam

logger = logging.getLogger(__name__)

class PDFRenderer:
    def __init__(self):
        # CSS Mejorado para Soportar Código y Matemáticas
        self.css_style = """
            @page { size: A4; margin: 2.5cm; }
            body { font-family: 'Helvetica', 'Arial', sans-serif; line-height: 1.5; color: #2c3e50; }
            
            .header { border-bottom: 2px solid #34495e; padding-bottom: 10px; margin-bottom: 30px; display: flex; justify-content: space-between; }
            .title { font-size: 24px; font-weight: bold; color: #2c3e50; }
            .meta { text-align: right; font-size: 12px; color: #7f8c8d; }
            
            .question-card { margin-bottom: 35px; break-inside: avoid; }
            .q-badge { 
                background: #34495e; color: #fff; padding: 4px 8px; 
                font-size: 10px; font-weight: bold; border-radius: 4px; 
                text-transform: uppercase; margin-right: 10px;
            }
            .q-header { font-size: 14px; font-weight: bold; margin-bottom: 10px; display: flex; align-items: center; }
            .q-body { margin-bottom: 15px; font-size: 14px; white-space: pre-line; }
            
            /* TIPO: TEST */
            .options-list { list-style: none; padding-left: 0; }
            .option-item { margin-bottom: 8px; padding: 8px; border: 1px solid #bdc3c7; border-radius: 4px; }
            .checkbox { display: inline-block; width: 12px; height: 12px; border: 1px solid #7f8c8d; margin-right: 10px; border-radius: 50%; }
            
            /* TIPO: CÓDIGO */
            .code-box { 
                background: #1e1e1e; color: #d4d4d4; 
                padding: 15px; border-radius: 6px; font-family: 'Courier New', monospace; 
                min-height: 100px; border-left: 5px solid #0984e3;
            }
            .code-label { color: #5dade2; font-size: 10px; margin-bottom: 5px; display: block; }
            
            /* TIPO: NUMÉRICO */
            .numeric-box { border: 2px dashed #95a5a6; padding: 15px; background: #fdfefe; margin-top: 10px; }
            .unit-hint { float: right; color: #7f8c8d; font-style: italic; font-size: 12px; }
            
            .footer { position: fixed; bottom: 0; width: 100%; text-align: center; font-size: 9px; color: #bdc3c7; }
        """

        self.html_template = """
        <!DOCTYPE html>
        <html>
        <head><style>{{ css }}</style></head>
        <body>
            <div class="header">
                <div class="title">{{ exam.config.course_id }}</div>
                <div class="meta">
                    <div>EXAMEN ADAPTATIVO</div>
                    <div>ID: {{ exam.id.split('-')[0] }}</div>
                    <div>Nivel: {{ exam.config.target_difficulty.value | upper }}</div>
                </div>
            </div>

            <div style="background:#ecf0f1; padding:10px; border-radius:4px; font-size:12px; margin-bottom:25px;">
                <strong>Instrucciones:</strong> Este examen ha sido generado para reforzar tus áreas de mejora.
                Justifica todas las respuestas numéricas.
            </div>

            {% for q in exam.questions %}
            <div class="question-card">
                <div class="q-header">
                    <span class="q-badge">{{ q.question_type.value }}</span>
                    <span>Pregunta {{ loop.index }}</span>
                    <span style="margin-left:auto; font-size:12px; color:#7f8c8d">
                          Dif: {{ q.difficulty.value }}
                    </span>
                </div>
                
                <div class="q-body">
                    {{ q.statement_latex | replace('\n', '<br>') }}
                </div>
                
                {% if q.question_type.value == 'multiple_choice' and q.validation_rules and q.validation_rules.type == 'choice' %}
                    <ul class="options-list">
                    {% for opt in q.validation_rules.options %}
                        <li class="option-item"><span class="checkbox"></span>{{ opt }}</li>
                    {% endfor %}
                    </ul>
                    
                {% elif q.question_type.value == 'code_editor' %}
                    <div class="code-box">
                        <span class="code-label">EDITOR PYTHON</span>
                        {% if q.code_context %}
                            {{ q.code_context }}
                        {% else %}
                            def solution():<br>
                            &nbsp;&nbsp;&nbsp;&nbsp;pass
                        {% endif %}
                    </div>
                    
                {% elif q.question_type.value == 'numeric_input' %}
                    <div class="numeric-box">
                        {% if q.validation_rules and q.validation_rules.allowed_units %}
                            <span class="unit-hint">Unidades: {{ q.validation_rules.allowed_units | join(', ') }}</span>
                        {% endif %}
                        <br><br>Result: ______________________
                    </div>
                    
                {% else %}
                    <div style="height:100px; border:1px solid #ccc;"></div>
                {% endif %}
            </div>
            {% endfor %}

            <div class="footer">Generado por TutorIA Engine | {{ date }}</div>
        </body>
        </html>
        """

    def render_to_bytes(self, exam: Exam) -> bytes:
        try:
            logger.info(f"📄 Renderizando documento PDF para: {exam.id}")
            template = Template(self.html_template)
            
            html_content = template.render(
                css=self.css_style,
                exam=exam,
                date=exam.created_at.strftime("%d/%m/%Y %H:%M")
            )
            
            # Generación Directa: Si falla aquí, es que falta configurar el Dockerfile
            return HTML(string=html_content).write_pdf()

        except Exception as e:
            logger.error(f"❌ Error Renderizando PDF: {e}")
            raise e