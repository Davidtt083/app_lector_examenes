import os
import json
from datetime import datetime
import google.generativeai as genai
from PIL import Image
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, Response
from .forms import RegistrationForm, LoginForm, TaskForm
from .models import User, Task
from . import db
from flask_login import login_user, logout_user, login_required, current_user
import io
import csv


def get_gemini_model():
    """Obtiene el modelo de Gemini configurado"""
    api_key = os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        raise ValueError("GOOGLE_API_KEY no está configurada. Por favor configúrala en el archivo .env")
    genai.configure(api_key=api_key)
    return genai.GenerativeModel('gemini-2.0-flash-exp')

bp = Blueprint('main', __name__)


@bp.route('/', methods=['GET', 'POST']) 
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Has iniciado sesión correctamente.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page) if next_page else redirect(url_for('main.dashboard'))
        else:
            flash('Correo o contraseña incorrectos.', 'danger')
            return redirect(url_for('main.index'))
            
    return render_template('index.html', form=form)


@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    form = RegistrationForm()
    if form.validate_on_submit():
        existing_user = User.query.filter((User.username == form.username.data) | (User.email == form.email.data)).first()
        if existing_user:
            flash('El nombre de usuario o el correo ya están en uso.', 'warning')
            return render_template('register.html', form=form)

        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Registro exitoso. Ya puedes iniciar sesión.', 'success')
        return redirect(url_for('main.index'))
    return render_template('register.html', form=form)


@bp.route('/login') 
def login():
    return redirect(url_for('main.index'))


@bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Has cerrado sesión.', 'info')
    return redirect(url_for('main.index'))


@bp.route('/dashboard')
@login_required
def dashboard():
    tasks = Task.query.filter_by(author=current_user).order_by(Task.created_at.desc()).all()
    return render_template('dashboard.html', tasks=tasks)

@bp.route('/create_exam', methods=['POST'])
@login_required
def create_exam():
    title = f"Examen de {current_user.username} - {datetime.now().strftime('%Y-%m-%d %H:%M')}"
    
    task = Task(
        title=title,
        description="Generado automáticamente", 
        author=current_user
    )
    db.session.add(task)
    db.session.commit()
    
    flash('Nuevo examen creado. Ahora puedes capturar la imagen.', 'info')
 
    return redirect(url_for('main.capture_exam', task_id=task.id))


@bp.route('/capture/<int:task_id>')
@login_required
def capture_exam(task_id):
    task = Task.query.get_or_404(task_id)
    if task.author != current_user:
        flash('No autorizado', 'danger')
        return redirect(url_for('main.dashboard'))
    return render_template('capture.html', task=task)


@bp.route('/process_image/<int:task_id>', methods=['POST'])
@login_required
def process_image(task_id):
    task = Task.query.get_or_404(task_id)
    if task.author != current_user:
        return jsonify({'error': 'No autorizado'}), 403

    if 'image' not in request.files:
        return jsonify({'error': 'No se envió imagen'}), 400
    
    file = request.files['image']
    if not file:
        return jsonify({'error': 'Archivo vacío'}), 400

    # Guardar imagen
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'exam_{task_id}_{timestamp}.jpg'
    filepath = os.path.join(current_app.root_path, 'static', 'uploads', filename)
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    file.save(filepath)

    try:
        print(f"Procesando imagen: {filepath}")
        
        # Abrir imagen con PIL
        image = Image.open(filepath)
        print("Imagen abierta correctamente")
        
        # Crear el modelo con visión
        model = genai.GenerativeModel('gemini-2.0-flash-exp')
        
        # Prompt para analizar el examen
        prompt = """Analiza esta imagen de un examen con alveolos (círculos de respuestas múltiples).

Por favor identifica:
1. El número de matrícula del estudiante (busca un número de identificación, puede estar en la parte superior)
2. Para cada pregunta visible, identifica qué alveolo está marcado o rellenado (A, B, C, D o E)

IMPORTANTE: 
- Solo incluye las respuestas que estén claramente marcadas
- Si un alveolo está rellenado, sombreado o tiene una marca visible, considéralo marcado
- Numera las preguntas en orden secuencial (1, 2, 3, etc.)

Responde ÚNICAMENTE con un objeto JSON en este formato exacto, sin texto adicional:
{
  "matricula": "número_de_matrícula_encontrado",
  "respuestas": [
    {"pregunta": 1, "respuesta": "A"},
    {"pregunta": 2, "respuesta": "B"}
  ]
}

Si no encuentras la matrícula, usa "NO_ENCONTRADA".
"""
        
        print("Enviando imagen a Gemini...")
        response = model.generate_content(
            [prompt, image],
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                max_output_tokens=2048,
            )
        )
        
        print(f"Respuesta de Gemini: {response.text}")
        
        # Limpiar y parsear la respuesta JSON
        result_text = response.text.strip()
        
        # Eliminar markdown si existe
        if result_text.startswith("```json"):
            result_text = result_text[7:]
        elif result_text.startswith("```"):
            result_text = result_text[3:]
        
        if result_text.endswith("```"):
            result_text = result_text[:-3]
        
        result_text = result_text.strip()
        
        # Parsear JSON
        result = json.loads(result_text)
        
        print(f"JSON procesado: {result}")
        
        # Validar estructura
        if 'matricula' not in result or 'respuestas' not in result:
            raise ValueError("El JSON debe contener 'matricula' y 'respuestas'")
        
        if not isinstance(result['respuestas'], list):
            raise ValueError("Las respuestas deben ser una lista")
        
        # Actualizar tarea con resultados
        task.matricula = result['matricula']
        task.respuestas = result['respuestas']
        task.imagen_path = os.path.join('uploads', filename)
        task.procesado = True
        
        print("Guardando en la base de datos...")
        db.session.commit()
        print("Guardado completado")

        return jsonify({
            'success': True,
            'matricula': task.matricula,
            'respuestas': task.respuestas,
            'imagen_url': url_for('static', filename=task.imagen_path)
        })

    except json.JSONDecodeError as e:
        print(f"Error al decodificar JSON: {e}")
        print(f"Texto recibido: {result_text}")
        return jsonify({
            'error': 'Error al procesar la respuesta de Gemini',
            'details': f'No se pudo parsear el JSON: {str(e)}'
        }), 500
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(f"Error: {str(e)}")
        print(f"Detalles: {error_details}")
        return jsonify({
            'error': str(e),
            'details': error_details
        }), 500


@bp.route('/view_results/<int:task_id>')
@login_required
def view_results(task_id):
    task = Task.query.get_or_404(task_id)
    if task.author != current_user:
        flash('No autorizado', 'danger')
        return redirect(url_for('main.dashboard'))
    
    if not task.procesado:
        flash('Este examen aún no ha sido procesado', 'warning')
        return redirect(url_for('main.dashboard'))
    
    return render_template('results.html', task=task)

@bp.route('/download_csv')
@login_required
def download_csv():
    """Genera y descarga un archivo CSV con los resultados de los exámenes procesados."""
    
    tasks = Task.query.filter_by(author=current_user, procesado=True).order_by(Task.created_at.desc()).all()

    if not tasks:
        flash('No hay exámenes procesados para descargar.', 'warning')
        return redirect(url_for('main.dashboard'))

    si = io.StringIO()
    writer = csv.writer(si)

    max_questions = 0
    if tasks:
        max_questions = max(len(task.respuestas) for task in tasks if task.respuestas)

    headers = ['Matricula'] + [f'Pregunta {i+1}' for i in range(max_questions)]
    writer.writerow(headers)
    for task in tasks:
        answers = [resp['respuesta'] for resp in task.respuestas]
        row = [task.matricula] + answers
        row.extend([''] * (max_questions - len(answers)))
        
        writer.writerow(row)

    output = si.getvalue()
    
    return Response(
        output,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=resultados_examenes.csv"}
    )