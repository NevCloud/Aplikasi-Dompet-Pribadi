"""gunakan link http://localhost:5000"""

from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
import mysql.connector
from mysql.connector import Error
from datetime import datetime, date, timedelta

app = Flask(__name__)
CORS(app)

# Database Configuration
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': '',  
    'database': 'dompet_ku'
}

def get_db_connection():
    try:
        return mysql.connector.connect(**DB_CONFIG)
    except Error as e:
        print(f"Error: {e}")
        return None

# API Routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/portfolios', methods=['GET'])
def get_portfolios():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM portopolio ORDER BY id")
    portfolios = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(portfolios)

@app.route('/api/portfolios', methods=['POST'])
def create_portfolio():
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO portopolio (nama, saldo, limit_harian, icon, color)
        VALUES (%s, %s, %s, %s, %s)
    """, (data.get('nama'), int(data.get('saldo', 0)), int(data.get('limit_harian', 0)), 
          data.get('icon', '💰'), data.get('color', 'success')))
    conn.commit()
    portfolio_id = cursor.lastrowid
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'id': portfolio_id})

@app.route('/api/portfolios/<int:id>', methods=['PUT'])
def update_portfolio(id):
    data = request.json
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor()
    updates = []
    values = []
    for field in ['nama', 'icon', 'color']:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(data[field])
    for field in ['saldo', 'limit_harian']:
        if field in data:
            updates.append(f"{field} = %s")
            values.append(int(data[field]))
    values.append(id)
    cursor.execute(f"UPDATE portopolio SET {', '.join(updates)} WHERE id = %s", values)
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/transactions', methods=['GET'])
def get_transactions():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT p.*, po.nama as portfolio_nama, po.icon as portfolio_icon, po.color as portfolio_color
        FROM pencacatan_pengeluaran p
        JOIN portopolio po ON p.id_porto = po.id
        ORDER BY p.waktu DESC LIMIT 100
    """)
    transactions = cursor.fetchall()
    cursor.close()
    conn.close()
    for t in transactions:
        t['waktu'] = t['waktu'].isoformat()
    return jsonify(transactions)

@app.route('/api/transactions', methods=['POST'])
def add_transaction():
    data = request.json
    id_porto = int(data.get('id_porto'))
    biaya = int(data.get('biaya_pengeluaran'))
    jenis = data.get('jenis', 'pengeluaran')
    
    if biaya <= 0:
        return jsonify({'error': 'Biaya harus lebih dari 0'}), 400
    
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT saldo FROM portopolio WHERE id = %s", (id_porto,))
    portfolio = cursor.fetchone()
    
    if not portfolio:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Portfolio tidak ditemukan'}), 404
    
    if jenis == 'pengeluaran' and portfolio['saldo'] < biaya:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Saldo tidak mencukupi'}), 400
    
    cursor.execute("""
        INSERT INTO pencacatan_pengeluaran (id_porto, biaya_pengeluaran, keterangan, jenis)
        VALUES (%s, %s, %s, %s)
    """, (id_porto, biaya, data.get('keterangan', ''), jenis))
    
    new_saldo = portfolio['saldo'] - biaya if jenis == 'pengeluaran' else portfolio['saldo'] + biaya
    cursor.execute("UPDATE portopolio SET saldo = %s WHERE id = %s", (new_saldo, id_porto))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True, 'new_saldo': new_saldo})

@app.route('/api/transactions/<int:id>', methods=['DELETE'])
def delete_transaction(id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT * FROM pencacatan_pengeluaran WHERE id = %s", (id,))
    transaction = cursor.fetchone()
    
    if not transaction:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Transaksi tidak ditemukan'}), 404
    
    cursor.execute("DELETE FROM pencacatan_pengeluaran WHERE id = %s", (id,))
    if transaction['jenis'] == 'pengeluaran':
        cursor.execute("UPDATE portopolio SET saldo = saldo + %s WHERE id = %s",
                      (transaction['biaya_pengeluaran'], transaction['id_porto']))
    else:
        cursor.execute("UPDATE portopolio SET saldo = saldo - %s WHERE id = %s",
                      (transaction['biaya_pengeluaran'], transaction['id_porto']))
    conn.commit()
    cursor.close()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/stats/daily', methods=['GET'])
def get_daily_stats():
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT 
            COALESCE(SUM(CASE WHEN jenis = 'pengeluaran' THEN biaya_pengeluaran ELSE 0 END), 0) as pengeluaran,
            COALESCE(SUM(CASE WHEN jenis = 'pemasukan' THEN biaya_pengeluaran ELSE 0 END), 0) as pemasukan
        FROM pencacatan_pengeluaran WHERE DATE(waktu) = %s
    """, (date.today(),))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    return jsonify(result)

@app.route('/api/stats/weekly', methods=['GET'])
def get_weekly_stats():
    today = date.today()
    week_ago = today - timedelta(days=6)
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT DATE(waktu) as date,
            COALESCE(SUM(CASE WHEN jenis = 'pengeluaran' THEN biaya_pengeluaran ELSE 0 END), 0) as pengeluaran
        FROM pencacatan_pengeluaran
        WHERE DATE(waktu) BETWEEN %s AND %s
        GROUP BY DATE(waktu) ORDER BY DATE(waktu)
    """, (week_ago, today))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    for r in results:
        r['date'] = r['date'].isoformat()
    return jsonify(results)

@app.route('/api/stats/monthly', methods=['GET'])
def get_monthly_stats():
    today = date.today()
    first_day = date(today.year, today.month, 1)
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""
        SELECT po.nama, po.icon, po.color,
            COALESCE(SUM(CASE WHEN p.jenis = 'pengeluaran' THEN p.biaya_pengeluaran ELSE 0 END), 0) as pengeluaran,
            COALESCE(SUM(CASE WHEN p.jenis = 'pemasukan' THEN p.biaya_pengeluaran ELSE 0 END), 0) as pemasukan
        FROM portopolio po
        LEFT JOIN pencacatan_pengeluaran p ON po.id = p.id_porto AND DATE(p.waktu) >= %s
        GROUP BY po.id, po.nama, po.icon, po.color
    """, (first_day,))
    results = cursor.fetchall()
    cursor.close()
    conn.close()
    return jsonify(results)

@app.route('/api/check-limit/<int:portfolio_id>', methods=['GET'])
def check_limit(portfolio_id):
    conn = get_db_connection()
    if not conn:
        return jsonify({'error': 'Database connection failed'}), 500
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT limit_harian FROM portopolio WHERE id = %s", (portfolio_id,))
    portfolio = cursor.fetchone()
    
    if not portfolio:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Portfolio tidak ditemukan'}), 404
    
    cursor.execute("""
        SELECT COALESCE(SUM(biaya_pengeluaran), 0) as total
        FROM pencacatan_pengeluaran
        WHERE id_porto = %s AND DATE(waktu) = %s AND jenis = 'pengeluaran'
    """, (portfolio_id, date.today()))
    result = cursor.fetchone()
    cursor.close()
    conn.close()
    
    limit_harian = portfolio['limit_harian']
    total_today = result['total']
    exceeded = limit_harian > 0 and total_today > limit_harian
    
    return jsonify({
        'limit': limit_harian,
        'spent': total_today,
        'exceeded': exceeded,
        'remaining': max(0, limit_harian - total_today)
    })

if __name__ == '__main__':
    print("="*50)
    print("Flask Dompet Ku Application")
    print("="*50)
    print("Open: http://localhost:5000")
    print("="*50)
    app.run(debug=True, host='0.0.0.0', port=5000)