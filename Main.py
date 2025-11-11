import random
from datetime import datetime
from io import BytesIO

from fpdf import FPDF
from flask import Flask, render_template, request, flash, redirect, url_for, send_file
from flask_sqlalchemy import SQLAlchemy

app = Flask(__name__)

# Configuración de conexión a MySQL usando PyMySQL
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://root:@localhost/airline_sales'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)


def generar_codigo_pnr():
    # Obtener la última reserva registrada
    ultima_reserva = Reserva.query.order_by(Reserva.id_reserva.desc()).first()

    if ultima_reserva and ultima_reserva.codigo_pnr.startswith('PNR'):
        # Extrae el número (por ejemplo, de 'PNR005' obtiene 5)
        numero = int(ultima_reserva.codigo_pnr[3:])
        nuevo_numero = numero + 1
    else:
        nuevo_numero = 1  # Si no hay reservas, empieza desde 1

    # Retorna el código con formato PNR + número de 3 dígitos
    return f"PNR{nuevo_numero:03d}"


def generar_precio_reserva():
    return round(random.uniform(100, 999), 2)


# Modelo de la tabla Vuelo
class Vuelo(db.Model):
    __tablename__ = 'Vuelo'
    id_vuelo = db.Column(db.Integer, primary_key=True)
    numero_vuelo = db.Column(db.String(10), unique=True, nullable=False)
    origen = db.Column(db.String(3), nullable=False)
    destino = db.Column(db.String(3), nullable=False)
    fecha_salida = db.Column(db.DateTime, nullable=False)
    fecha_llegada = db.Column(db.DateTime, nullable=False)
    aeronave = db.Column(db.String(50))
    asientos_totales = db.Column(db.Integer, nullable=False)
    asientos_disponibles = db.Column(db.Integer, nullable=False)
    estado = db.Column(db.String(20), default='PROGRAMADO')


class Reserva(db.Model):
    __tablename__ = 'Reserva'

    id_reserva = db.Column(db.Integer, primary_key=True)
    codigo_pnr = db.Column(db.String(10), unique=True, nullable=False)
    id_pasajero = db.Column(db.Integer, db.ForeignKey('Pasajero.id_pasajero', ondelete='RESTRICT', onupdate='CASCADE'),
                            nullable=False)
    id_vuelo = db.Column(db.Integer, db.ForeignKey('Vuelo.id_vuelo', ondelete='RESTRICT', onupdate='CASCADE'),
                         nullable=False)
    fecha_reserva = db.Column(db.DateTime, default=datetime.utcnow)
    estado = db.Column(db.String(20), nullable=False, default='PENDIENTE')
    total_reserva = db.Column(db.Numeric(10, 2), default=0)

    pasajero = db.relationship('Pasajero', backref='reservas', lazy=True)
    vuelo = db.relationship('Vuelo', backref='reservas', lazy=True)


class Pasajero(db.Model):
    __tablename__ = 'Pasajero'

    id_pasajero = db.Column(db.Integer, primary_key=True)
    dni = db.Column(db.String(15), unique=True, nullable=False)
    nombres = db.Column(db.String(100), nullable=False)
    apellidos = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False)
    telefono = db.Column(db.String(20))
    fecha_registro = db.Column(db.Date, default=datetime.utcnow)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/buscar_vuelos', methods=['POST'])
def buscar_vuelos():
    origen = request.form['origen'].upper()
    destino = request.form['destino'].upper()

    vuelos = Vuelo.query.filter_by(origen=origen, destino=destino).all()

    return render_template('resultados.html', vuelos=vuelos, origen=origen, destino=destino)


@app.route('/reservas')
def reservas():
    vuelos = Vuelo.query.filter_by(estado='PROGRAMADO').all()
    return render_template('reserva.html', vuelos=vuelos)


@app.route('/registrores', methods=['POST'])
def crear_reserva():
    id_pasajero = request.form['id_pasajero']
    id_vuelo = request.form['id_vuelo']

    # Buscar el vuelo correspondiente
    vuelo = Vuelo.query.get_or_404(id_vuelo)

    # Verificar que haya asientos disponibles
    if vuelo.asientos_disponibles <= 0:
        flash('No hay asientos disponibles para este vuelo.')
        return redirect(url_for('reservas'))  # o a la página que quieras

    # Crear la nueva reserva
    nueva_reserva = Reserva(
        codigo_pnr=generar_codigo_pnr(),
        id_pasajero=id_pasajero,
        id_vuelo=id_vuelo,
        estado='PENDIENTE',
        total_reserva=generar_precio_reserva()
    )

    # Disminuir los asientos disponibles del vuelo
    vuelo.asientos_disponibles -= 1

    # Guardar cambios en la DB
    db.session.add(nueva_reserva)
    db.session.commit()

    return render_template(
        'allreservas.html',
        codigo_pnr=nueva_reserva.codigo_pnr,
        id_vuelo=nueva_reserva.id_vuelo,
        id_pasajero=nueva_reserva.id_pasajero,
        estado=nueva_reserva.estado,
        total_reserva=nueva_reserva.total_reserva,
        fecha_reserva=nueva_reserva.fecha_reserva,
        reserva=nueva_reserva
    )


@app.route('/voucher/<int:id_reserva>')
def generar_voucher(id_reserva):
    reserva = Reserva.query.get_or_404(id_reserva)

    # Crear PDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", 'B', 16)
    pdf.cell(0, 10, "Voucher de Reserva", ln=True, align='C')
    pdf.set_font("Helvetica", '', 12)
    pdf.cell(0, 10, f"PNR: {reserva.codigo_pnr}", ln=True)
    pdf.cell(0, 10, f"Pasajero: {reserva.pasajero.nombres} {reserva.pasajero.apellidos}", ln=True)
    pdf.cell(0, 10, f"Vuelo: {reserva.vuelo.numero_vuelo}", ln=True)
    pdf.cell(0, 10, f"Origen: {reserva.vuelo.origen}", ln=True)
    pdf.cell(0, 10, f"Destino: {reserva.vuelo.destino}", ln=True)
    pdf.cell(0, 10, f"Fecha de salida: {reserva.vuelo.fecha_salida}", ln=True)
    pdf.cell(0, 10, f"Total: S/{reserva.total_reserva}", ln=True)

    pdf_buffer = BytesIO()
    pdf.output(pdf_buffer)
    pdf_buffer.seek(0)

    return send_file(
        pdf_buffer,
        as_attachment=True,
        download_name=f"voucher_{reserva.codigo_pnr}.pdf",
        mimetype='application/pdf'
    )


if __name__ == '__main__':
    app.run(debug=True)
