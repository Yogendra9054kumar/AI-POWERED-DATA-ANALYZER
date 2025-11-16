from flask import Flask, render_template, request, redirect, url_for, session, make_response, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
import os
import matplotlib
matplotlib.use('Agg')  # Use non-GUI backend for Flask
import matplotlib.pyplot as plt
import pandas as pd
# removed pdfkit import (we now use ReportLab)
import base64
import matplotlib.pyplot as plt
from io import BytesIO
from datetime import datetime
import uuid
import shutil
import urllib.parse
# import reportlab

# NEW: ReportLab imports for PDF generation
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image as RLImage, Table as RLTable, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch

# ------------------------- App Configuration -------------------------
app = Flask(__name__)
app.secret_key = 'supersecretkey'
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['ALLOWED_EXTENSIONS'] = {'csv', 'xlsx'}

# SQLite Database Configuration
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///users.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# Ensure static charts folder exists
CHARTS_DIR = os.path.join('static', 'charts')
os.makedirs(CHARTS_DIR, exist_ok=True)

# ------------------------- Database Model -------------------------
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

# ------------------------- Utility Functions -------------------------
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

def safe_name(s: str):
    """Make a filesystem-safe short name."""
    return "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in s)[:100]

def save_histogram_png(df, col, outfile_path):
    plt.figure(figsize=(6,4))
    try:
        # dropna to avoid plotting errors
        data = df[col].dropna()
        plt.hist(data, bins=30, edgecolor='black')
        plt.title(f'Histogram of {col}')
        plt.xlabel(col)
        plt.ylabel('Count')
        plt.tight_layout()
        plt.savefig(outfile_path, dpi=150)
    finally:
        plt.close()

def save_scatter_png(df, xcol, ycol, outfile_path):
    plt.figure(figsize=(6,4))
    try:
        plt.scatter(df[xcol], df[ycol], alpha=0.7, s=20)
        plt.title(f'{xcol} vs {ycol}')
        plt.xlabel(xcol)
        plt.ylabel(ycol)
        plt.tight_layout()
        plt.savefig(outfile_path, dpi=150)
    finally:
        plt.close()

def imgfile_to_base64(img_path):
    with open(img_path, 'rb') as f:
        data = f.read()
    return base64.b64encode(data).decode('utf-8')

def generate_insights_text(df):
    insights_text = []
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()

    if numeric_cols:
        for col in numeric_cols:
            mean = df[col].mean()
            median = df[col].median()
            std = df[col].std()
            min_val = df[col].min()
            max_val = df[col].max()
            insights_text.append(
                f"Column '{col}': mean={mean:.2f}, median={median:.2f}, std={std:.2f}, min={min_val}, max={max_val}."
            )
    else:
        insights_text.append("No numeric columns found for summary statistics.")

    if len(numeric_cols) > 1:
        corr_matrix = df[numeric_cols].corr().abs()
        corr_pairs = []
        for i in range(len(numeric_cols)):
            for j in range(i + 1, len(numeric_cols)):
                corr_pairs.append((numeric_cols[i], numeric_cols[j], corr_matrix.iloc[i, j]))
        corr_pairs.sort(key=lambda x: x[2], reverse=True)
        for col1, col2, corr_val in corr_pairs[:5]:
            insights_text.append(f"Columns '{col1}' and '{col2}' have a correlation of {corr_val:.2f}.")
    else:
        insights_text.append("Not enough numeric columns for correlations.")

    if numeric_cols:
        for col in numeric_cols:
            Q1 = df[col].quantile(0.25)
            Q3 = df[col].quantile(0.75)
            IQR = Q3 - Q1
            outlier_count = df[(df[col] < Q1 - 1.5 * IQR) | (df[col] > Q3 + 1.5 * IQR)][col].count()
            insights_text.append(f"Column '{col}' has {int(outlier_count)} outliers (IQR method).")
    else:
        insights_text.append("No numeric columns to check for outliers.")

    return insights_text

# ------------------------- Authentication Routes -------------------------
@app.route('/')
def home():
    if 'user' in session:
        return redirect(url_for('index'))  # Go to upload page directly
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        name = request.form['name'].strip()
        password = request.form['password']

        if not email or not name or not password:
            flash('Please fill all fields', 'warning')
            return redirect(url_for('signup'))

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already exists. Please login.', 'warning')
            return redirect(url_for('login'))

        hashed_password = generate_password_hash(password)
        new_user = User(name=name, email=email, password=hashed_password)
        db.session.add(new_user)
        db.session.commit()

        flash('Signup successful! Please login.', 'success')
        return redirect(url_for('login'))
    return render_template('signup.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email'].strip().lower()
        password = request.form['password']

        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password, password):
            session['user'] = user.email
            session['name'] = user.name
            flash(f'Welcome back, {user.name}!', 'success')
            return redirect(url_for('index'))  # redirect to index (main upload)
        else:
            flash('Invalid email or password', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user', None)
    session.pop('name', None)
    flash('Logged out successfully', 'info')
    return redirect(url_for('login'))

# ------------------------- Main Index Page (Upload Page) -------------------------
@app.route('/index', methods=['GET', 'POST'])
def index():
    if 'user' not in session:
        return redirect(url_for('login'))

    if request.method == 'POST':
        if 'dataset' not in request.files:
            flash("No file part", "danger")
            return redirect(url_for('index'))
        file = request.files['dataset']
        if file.filename == '':
            flash("No file selected", "warning")
            return redirect(url_for('index'))
        if file and allowed_file(file.filename):
            os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(filepath)
            flash(f"Dataset '{file.filename}' uploaded successfully!", "success")
            return redirect(url_for('dashboard'))
        else:
            flash("File type not allowed. Only CSV and Excel supported.", "danger")
    return render_template('index.html', title='AI Data Insight Platform')

# ------------------------- Dashboard & File Handling -------------------------
@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    # default empty dashboard
    return render_template('dashboard.html', tables="<p>No dataset uploaded yet</p>",
                           filename="No file", histograms=[], scatters=[], insights_text=[])

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'user' not in session:
        return redirect(url_for('login'))

    if 'dataset' not in request.files:
        return "No file part"
    file = request.files['dataset']
    if file.filename == '':
        return "No file selected"
    if file and allowed_file(file.filename):
        os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)

        # Read dataset
        if file.filename.endswith('.csv'):
            df = pd.read_csv(filepath)
        else:
            df = pd.read_excel(filepath)

        table_html = df.head(10).to_html(classes='table table-striped', index=False)
        numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()

        # Generate histograms and save as pngs in static/charts
        histograms = []
        for col in numeric_cols:
            unique_id = uuid.uuid4().hex
            safe_col = safe_name(col)
            fname = f"hist_{safe_name(file.filename)}_{safe_col}_{unique_id}.png"
            outpath = os.path.join(CHARTS_DIR, fname)
            save_histogram_png(df, col, outpath)
            url = url_for('static', filename=f"charts/{fname}")
            histograms.append(f"<img src='{url}' class='img-fluid' alt='Histogram of {col}'>")

        # Generate scatter plots for first few numeric column pairs
        scatters = []
        for i in range(len(numeric_cols) - 1):
            xcol = numeric_cols[i]
            ycol = numeric_cols[i + 1]
            unique_id = uuid.uuid4().hex
            fname = f"scatter_{safe_name(file.filename)}_{safe_name(xcol)}_vs_{safe_name(ycol)}_{unique_id}.png"
            outpath = os.path.join(CHARTS_DIR, fname)
            save_scatter_png(df, xcol, ycol, outpath)
            url = url_for('static', filename=f"charts/{fname}")
            scatters.append(f"<img src='{url}' class='img-fluid' alt='Scatter {xcol} vs {ycol}'>")
            if i >= 3:  # limit to 4 scatters
                break

        # Generate human-readable AI-style insights
        insights_text = generate_insights_text(df)

        return render_template('dashboard.html',
                               tables=table_html,
                               filename=file.filename,
                               histograms=histograms,
                               scatters=scatters,
                               insights_text=insights_text)
    return "File type not allowed. Only CSV and Excel supported."

# ------------------------- Insights Page -------------------------
@app.route('/insights')
def insights():
    if 'user' not in session:
        return redirect(url_for('login'))
    return render_template('insights.html', title='AI Data Insights')

# ------------------------- PDF Generation (ReportLab) -------------------------
@app.route('/download_pdf/<filename>')
def download_pdf(filename):
    if 'user' not in session:
        return redirect(url_for('login'))

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not os.path.exists(filepath):
        return "File not found"

    # Read dataset
    df = pd.read_csv(filepath) if filename.endswith('.csv') else pd.read_excel(filepath)
    numeric_cols = df.select_dtypes(include=['int64', 'float64']).columns.tolist()

    # Generate PNGs for charts to include in PDF (use same functions)
    pdf_image_paths = []
    # histograms (limit to available numeric columns)
    for col in numeric_cols:
        unique_id = uuid.uuid4().hex
        fname = f"pdf_hist_{safe_name(filename)}_{safe_name(col)}_{unique_id}.png"
        outpath = os.path.join(CHARTS_DIR, fname)
        save_histogram_png(df, col, outpath)
        pdf_image_paths.append({'type': 'hist', 'col': col, 'path': outpath})
    # scatters (limit to 4)
    for i in range(len(numeric_cols) - 1):
        xcol = numeric_cols[i]
        ycol = numeric_cols[i + 1]
        unique_id = uuid.uuid4().hex
        fname = f"pdf_scatter_{safe_name(filename)}_{safe_name(xcol)}_vs_{safe_name(ycol)}_{unique_id}.png"
        outpath = os.path.join(CHARTS_DIR, fname)
        save_scatter_png(df, xcol, ycol, outpath)
        pdf_image_paths.append({'type': 'scatter', 'col': f"{xcol} vs {ycol}", 'path': outpath})
        if i >= 3:
            break

    insights_text = generate_insights_text(df)

    # Build PDF using ReportLab
    buffer = BytesIO()
    # Use A4 portrait; if lots of charts you can switch to landscape
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    styles = getSampleStyleSheet()
    story = []

    # Title
    title_style = styles['Title']
    story.append(Paragraph("AI Data Insight Report", title_style))
    story.append(Spacer(1, 12))

    # Filename and generation time
    meta_style = styles['Normal']
    gen_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    story.append(Paragraph(f"<b>Filename:</b> {filename}", meta_style))
    story.append(Paragraph(f"<b>Generated:</b> {gen_time}", meta_style))
    story.append(Spacer(1, 12))

    # Dataset preview table (first 10 rows)
    try:
        preview = df.head(10)
        # Prepare table data (headers + rows)
        table_data = [list(preview.columns)]
        for _, row in preview.iterrows():
            # convert each value to string to avoid ReportLab issues
            table_data.append([str(x) for x in row.tolist()])

        tbl = RLTable(table_data, repeatRows=1)
        tbl_style = TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#198754")),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1, -1), 8),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
        ])
        tbl.setStyle(tbl_style)
        story.append(Paragraph("<b>Dataset Preview (first 10 rows)</b>", styles['Heading3']))
        story.append(Spacer(1,6))
        story.append(tbl)
        story.append(Spacer(1,12))
    except Exception as e:
        # If table building fails, include a simple message instead (do not crash)
        story.append(Paragraph("Could not render dataset preview table.", meta_style))
        story.append(Spacer(1,12))

    # Insert histograms and scatter images
    if pdf_image_paths:
        story.append(Paragraph("<b>Charts</b>", styles['Heading3']))
        story.append(Spacer(1,6))
        for item in pdf_image_paths:
            img_path = item['path']
            if os.path.exists(img_path):
                # Fit image width to page width minus margins
                max_width = A4[0] - doc.leftMargin - doc.rightMargin  # available width
                # Create RL Image and scale maintaining aspect ratio
                try:
                    img = RLImage(img_path)
                    # scale image to max width (keep aspect)
                    iw, ih = img.wrap(0, 0)
                    if iw > max_width:
                        scale = max_width / iw
                        img.drawWidth = iw * scale
                        img.drawHeight = ih * scale
                    img.hAlign = 'CENTER'
                    story.append(Paragraph(f"{item.get('col')}", styles['Normal']))
                    story.append(Spacer(1,4))
                    story.append(img)
                    story.append(Spacer(1,12))
                except Exception as e:
                    # if image can't be loaded just add a message
                    story.append(Paragraph(f"Could not load image for {item.get('col')}.", meta_style))
                    story.append(Spacer(1,6))
    else:
        story.append(Paragraph("No numeric charts available.", meta_style))
        story.append(Spacer(1,12))

    # Insights section
    story.append(Paragraph("<b>Dataset Insights</b>", styles['Heading3']))
    story.append(Spacer(1,6))
    if insights_text:
        for ins in insights_text:
            # Keep individual insight lines short if possible
            story.append(Paragraph(ins, styles['Normal']))
            story.append(Spacer(1,4))
    else:
        story.append(Paragraph("No insights available.", styles['Normal']))

    # Footer / page number can be added with a custom onLater callback if desired (skipped for brevity)

    # Build PDF
    try:
        doc.build(story)
        pdf_value = buffer.getvalue()
        buffer.seek(0)
        response = make_response(pdf_value)
        response.headers['Content-Type'] = 'application/pdf'
        safe_fname = urllib.parse.quote(f"{filename}_report.pdf")
        response.headers['Content-Disposition'] = f'attachment; filename="{safe_fname}"'
        return response
    except Exception as e:
        # Return a helpful error message and the rendered HTML as fallback
        err_msg = str(e)
        help_text = (
            "<h3>PDF generation failed (ReportLab)</h3>"
            "<p>Reason: <code>{}</code></p>"
            "<p>Please check server logs for more details.</p>"
            "<p>Below is the HTML report (view & save manually):</p><hr>"
        ).format(err_msg)
        rendered = render_template('dashboard_pdf.html',
                                   tables=df.head(10).to_html(classes='table table-striped', index=False),
                                   filename=filename,
                                   histograms=[f"data:image/png;base64,{imgfile_to_base64(p['path'])}" for p in pdf_image_paths if os.path.exists(p['path'])],
                                   scatters=[],
                                   insights_text=insights_text)
        return help_text + rendered, 500

# ------------------------- Initialize Database -------------------------
with app.app_context():
    db.create_all()
    if not User.query.filter_by(email='admin@example.com').first():
        admin = User(name='Admin', email='admin@example.com',
                     password=generate_password_hash('admin123'))
        db.session.add(admin)
        db.session.commit()

# ------------------------- Run -------------------------
if __name__ == '__main__':
    app.run(debug=True)
