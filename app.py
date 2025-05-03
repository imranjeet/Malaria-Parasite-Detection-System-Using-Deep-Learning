from flask import Flask, render_template, request, redirect, url_for, flash, session, make_response, jsonify
from mysql.connector import connect, Error
from flask_wtf.file import DataRequired
from wtforms import Form, StringField, PasswordField, validators, SubmitField, SelectField
from wtforms.fields import EmailField, DateTimeLocalField  
from passlib.hash import sha256_crypt
from keras.preprocessing import image as i1 # type: ignore
from keras import models
from weasyprint import HTML
import tempfile


from functools import wraps
from flask_mail import Mail
import os, string, random, cv2, pdfkit, smtplib, uuid
from PIL import Image
import numpy as np

app = Flask(__name__)

# Database configuration
db_config = {
    'host': 'localhost',
    'user': 'root',
    'password': '',
    'database': 'test'
}

app.config['INITIAL_FILE_UPLOADS'] = os.path.join('static', 'img', 'uploads')
app.config['MAIL_SERVER']='smtp.gmail.com'
app.config['MAIL_PORT']= 587  
app.config['MAIL_USE_TLS']= True
app.config['MAIL_USERNAME']= os.environ.get('EMAIL_USER') 
app.config['MAIL_PASSWORD']= os.environ.get('EMAIL_PASS')

mail = Mail(app)

# Load ML model
try:
    model = models.load_model(os.path.join('static', 'models', 'malaria_detection_model.h5'))
    print(f"Successfully model loaded")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None

if model:
    print("Model loaded successfully")
    print("Input shape:", model.input_shape)
    print("Output shape:", model.output_shape)
    
# dummy_input = np.zeros((1, 224, 224, 3))
# result = model.predict(dummy_input)
# print("Prediction on blank image:", result)

def get_db_connection():
    try:
        connection = connect(**db_config)
        return connection
    except Error as e:
        print(f"Error connecting to MySQL: {e}")
        return None

@app.route("/")
def index():
    return render_template('home.html')

@app.route('/about')
def about():
    return render_template('about.html')

ALLOWED_EXTENSIONS = set(['png', 'jpg', 'jpeg'])

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# function to classify images
def predict_label(img_path):
    i = i1.load_img(img_path, target_size=(50, 50))
    i = cv2.imread(img_path)
    resized = cv2.resize(i, (50, 50))
    i = i1.img_to_array(resized) / 255.0
    i = i.reshape(1, 50, 50, 3)
    result = model.predict(i)
    a = round(result[0, 0], 2) * 100
    b = round(result[0, 1], 2) * 100
    probability = [a, b]
    app.logger.info(a)
    app.logger.info(b)
    app.logger.info(result)    
    threshold = 10
    
    if a > threshold or b > threshold:
        ind = np.argmax(result)
        classes = ['Uninfected', 'Infected']
        return classes[ind], probability[ind]
    else:
        return 'Invalid Image', 0


class RegisterForm(Form):
    name = StringField('Full Name')
    speciality = StringField('Speciality')
    cnic = StringField('CNIC')
    username = StringField('Username')
    email = StringField('Email Address')
    password = PasswordField('Password')
    confirm = PasswordField('Confirm Password')

class ForgotForm(Form):
    email = EmailField('Email Address',[validators.DataRequired(),validators.Email()])

class PasswordResetForm(Form):
    password = PasswordField('Password',[validators.DataRequired(),validators.Length(min=6,max=50),
                                        validators.EqualTo('confirm',message='Password do not match')])
    confirm = PasswordField('Confirm Password',[validators.DataRequired()])

@app.route('/register',methods=['GET','POST'])
def register():
    form = RegisterForm(request.form)
    if request.method == 'POST' and form.validate():
        name = form.name.data
        email = form.email.data
        username = form.username.data
        speciality = form.speciality.data
        cnic = form.cnic.data
        password = sha256_crypt.encrypt(str(form.password.data))

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                
                
                # Check if username exists
                cursor.execute("SELECT username FROM user WHERE username=%s", (username,))
                result1 = cursor.fetchone()
                
                # Check if email exists
                cursor.execute("SELECT email FROM user WHERE email=%s", (email,))
                result2 = cursor.fetchone()
                
                # Check if CNIC exists
                cursor.execute("SELECT cnic FROM user WHERE cnic=%s", (cnic,))
                result3 = cursor.fetchone()

                if result1:
                    flash("Username already exists",'danger')
                    return render_template('register.html',form=form)
                elif result2:
                    flash("An account with this email already exists",'danger')
                    return render_template('register.html',form=form)
                elif result3:
                    flash("An account with this CNIC already exists",'danger')
                    return render_template('register.html',form=form)
                else:
                    cursor.execute("INSERT INTO user(name,cnic,speciality,email,username,password) VALUES(%s,%s,%s,%s,%s,%s)",
                                (name,cnic,speciality,email,username,password))
                    connection.commit()
                    flash("You're registration request has been sent",'success')
                    return redirect(url_for('login'))
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')
    return render_template('register.html',form=form)

@app.route('/login',methods=['GET','POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password_candidate = request.form['password']
        
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT * from user WHERE username = %s", (username,))
                result = cursor.fetchone()

                if result:
                    password = result['password']

                    if sha256_crypt.verify(password_candidate, password):
                        if result['user_type'] == 1:
                            session['logged_in'] = True
                            session['username'] = username
                            session['user_type'] = 1
                            session['id'] = result['id']
                            app.logger.info(session['id']) 
                            flash('You are now logged in','success')
                            return redirect(url_for('admin'))
                        elif result['user_type'] == 0:
                            session['logged_in'] = True
                            session['username'] = username
                            session['user_type'] = 0
                            session['id'] = result['id']
                            flash('You are now logged in','success')
                            return redirect(url_for('dashboard'))
                        elif result['user_type'] == -1:
                            error = "Request hasn't been accepted yet"
                            return render_template('login.html',error=error)
                    else:
                        error = 'Invalid Login'
                        return render_template('login.html',error=error)
                else:
                    error = 'Username not found'
                    return render_template('login.html',error=error)
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')
    return render_template('login.html')

def is_logged_in(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if 'logged_in' in session:
            return f(*args,**kwargs)
        else:
            flash('Unauthorized, Please login','danger')
            return redirect(url_for('login'))
    return wrap

def redirect_url(default='index'):
    return request.args.get('next') or request.referrer or url_for(default)

def is_admin_in(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if session['user_type'] == 1:
            return f(*args,**kwargs)
        elif session['user_type'] == 0:
            return f(*args,**kwargs)
        else:
            flash('Unauthorized Access','danger')
            return redirect(redirect_url('dashboard'))
    return wrap

def is_physician_in(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if session['user_type'] == 0:
            return f(*args,**kwargs)
        elif session['user_type'] == 1:
            return f(*args,**kwargs)
        else:
            flash('Unauthorized Access','danger')
            return redirect(redirect_url('admin'))
    return wrap

@app.route('/user')
@is_logged_in
@is_admin_in
def user():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM user WHERE user_type='0'")
            users = cursor.fetchall()

            if users:
                return render_template('users.html', user=users)
            else:
                msg = "No Users Found"
                return render_template('users.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('users.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('users.html')

@app.route('/user_requests')
@is_logged_in
@is_admin_in
def userRequests():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM user WHERE user_type='-1'")
            users = cursor.fetchall()

            if users:
                return render_template('user_requests.html', users=users)
            else:
                msg = 'No User Requests Found'
                return render_template('user_requests.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('user_requests.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('user_requests.html')

@app.route('/user_requests/<string:id>',methods=['GET','POST'])
@is_logged_in
@is_admin_in
def acceptUser(id):
    if request.method == 'POST':
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT email from user WHERE id=%s", (id,))
                data = cursor.fetchone()
                cursor.execute("UPDATE user SET user_type='0' WHERE id=%s", (id,))
                connection.commit()
                flash('Request Accepted','success')
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')
        return redirect(url_for('userRequests'))

@app.route('/delete_user_request/<string:id>',methods=['POST'])
@is_logged_in
@is_admin_in
def deleteUserRequest(id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE from user WHERE id=%s", (id,))
            connection.commit()
            flash('Request Deleted','success')
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
    return redirect(url_for('userRequests'))

@app.route('/delete_user/<string:id>', methods=['POST'])
@is_logged_in
@is_admin_in
def delete_user(id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM user WHERE id=%s", (id,))
            connection.commit()
            flash('User Deleted','success')
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
    return redirect(url_for('user'))

@app.route('/profile')
@is_logged_in
def profile():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            id = session['id']
            cursor.execute("SELECT * FROM user WHERE id=%s", (id,))
            user = cursor.fetchall()

            if user:
                return render_template('profile.html', user=user, id=id)
            else:
                msg = "No User Found"
                return render_template('profile.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('profile.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('profile.html')

@app.route('/admin')
@is_logged_in
@is_admin_in
def admin():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            
            # Get user count
            cursor.execute("SELECT COUNT(id) AS users FROM user WHERE user_type='0'")
            data = cursor.fetchone()
            users = data['users']
            
            # Get patient count
            cursor.execute("SELECT COUNT(p_id) AS all_patients FROM patients")
            data = cursor.fetchone()
            patients = data['all_patients']
            
            # Get user records
            cursor.execute("SELECT * FROM user WHERE user_type='0'")
            user_records = cursor.fetchall()
            
            # Get disease reports count
            cursor.execute("SELECT COUNT(disease_id) AS disease_reports FROM disease")
            data = cursor.fetchone()
            reports = data['disease_reports']
            
            # Get patient records
            cursor.execute("SELECT *,concat('P21-',lpad(patients.p_id,5,'0')) AS p_id2 FROM patients")
            patient_records = cursor.fetchall()
            
            return render_template('admin_dashboard.html',
                                patient_records=patient_records,
                                reports=reports,
                                user_records=user_records,
                                patients=patients,
                                users=users)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('admin_dashboard.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('admin_dashboard.html')

@app.route('/logout')
@is_logged_in
def logout():
    session.clear()
    flash('You are now logged out','success')
    return redirect(url_for('login'))

@app.route('/dashboard')
@is_logged_in
@is_physician_in
def dashboard():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            id = session['id']
            
            # Get patient records
            cursor.execute("SELECT *,concat('P21-',lpad(p_id,5,'0')) AS p_id2 FROM patients WHERE user_id=%s", (id,))
            patient_records = cursor.fetchall()
            
            # Get patient count
            cursor.execute("SELECT COUNT(p_id) AS all_patients FROM patients WHERE user_id=%s", (id,))
            data = cursor.fetchone()
            patients = data['all_patients']
            
            # Get reports count
            cursor.execute("SELECT COUNT(disease_id) AS all_reports FROM disease WHERE patient_id in (SELECT p_id from patients WHERE user_id=%s)", (id,))
            data = cursor.fetchone()
            reports = data['all_reports']
            
            return render_template('dashboard.html',
                                reports=reports,
                                patients=patients,
                                patient_records=patient_records)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('dashboard.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('dashboard.html')

@app.route('/forgot',methods=['GET','POST'])
def forgot():
    form = ForgotForm(request.form)

    if request.method == 'POST' and form.validate():
        email = form.email.data
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT * from user where email=%s", (email,))
                data = cursor.fetchone()

                if data:
                    token = str(uuid.uuid4())
                    cursor.execute("UPDATE user SET token=%s WHERE email=%s", (token, email))
                    connection.commit()
                    
                    TEXT = "We have received a request for password reset.\n\n To reset your password, please click on this link:\n http://127.0.0.1:5000/reset/"+token
                    SUBJECT = "Password reset request"
                    message = 'Subject: {}\n\n{}'.format(SUBJECT, TEXT)
                    server = smtplib.SMTP("smtp.gmail.com",587)
                    server.starttls()
                    server.login('khalid.ghulbi22@gmail.com','ckcoeaccbgvdzclx')
                    server.sendmail('email',email,message)
                    
                    msg = "You have received a password reset email"
                    return render_template('forgot.html',form=form,msg=msg)
                else:
                    error = "A user account with this email doesn't exist"
                    return render_template('forgot.html',form=form,error=error)
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')
    return render_template('forgot.html',form=form)

@app.route('/reset/<string:token>',methods=['GET','POST'])
def resetPassword(token):
    form = PasswordResetForm(request.form)
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * from user WHERE token=%s", (token,))
            result = cursor.fetchone()
            
            if result:
                if request.method == 'POST' and form.validate():
                    password = sha256_crypt.encrypt(str(form.password.data))
                    cursor.execute("UPDATE user SET password=%s, token='' WHERE token=%s", (password, token))
                    connection.commit()
                    flash('Password successfully changed','success')
                    return redirect(url_for('login'))
                return render_template('reset_password.html',form=form)
            else:
                flash('Your token is invalid','danger')
                return redirect(url_for('login'))
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return redirect(url_for('login'))
    
@app.route('/patients')
@is_logged_in
@is_admin_in
@is_physician_in
def patients():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            id = session['id']
            cursor.execute("SELECT *,concat('P21-',lpad(p_id,5,'0')) as p_id2 FROM patients WHERE user_id=%s", (id,))
            patients = cursor.fetchall()

            if patients:
                return render_template('patients.html', patients=patients)
            else:
                msg = "No Patients Found"
                return render_template('patients.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('patients.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('patients.html')

class PatientForm(Form):
    user_id = StringField('User ID')
    p_name = StringField('Full Name')
    p_dob = StringField('Date of Birth')
    p_age = StringField('Age')
    p_docname = StringField('Doctor Name')
    p_gender = SelectField(u'Gender',choices = [('Male','Male'),('Female','Female')])

@app.route('/add_patient',methods = ['GET', 'POST'])
@is_logged_in
@is_physician_in
def add_patient():
    form = PatientForm(request.form)
    if request.method == 'POST' and form.validate():
        p_name = form.p_name.data
        p_dob = form.p_dob.data
        p_age = form.p_age.data
        p_docname = form.p_docname.data
        p_gender = form.p_gender.data

        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("INSERT INTO patients(p_name, user_id, p_dob, p_age,p_docname,p_gender) VALUES(%s,%s,%s,%s,%s,%s)", 
                              (p_name, session['id'], p_dob, p_age, p_docname, p_gender))
                connection.commit()
                flash('Patient Added','success')
                return redirect(url_for('patients'))
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')
    return render_template('add_patient.html',form=form)

@app.route('/edit_patient/<string:id>',methods = ['GET', 'POST'])
@is_logged_in
@is_physician_in
def edit_patient(id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM patients WHERE p_id=%s", (id,))
            patient = cursor.fetchone()

            form = PatientForm(request.form)
            form.user_id.data = patient['user_id']
            form.p_name.data = patient['p_name']
            form.p_dob.data = patient['p_dob']
            form.p_age.data = patient['p_age']
            form.p_docname.data = patient['p_docname']
            form.p_gender.data = patient['p_gender']

            if request.method == 'POST' and form.validate():
                p_name = request.form['p_name']
                p_dob = request.form['p_dob']
                p_age = request.form['p_age']
                p_docname = request.form['p_docname']
                p_gender = request.form['p_gender']

                cursor.execute("UPDATE patients SET p_name=%s, p_dob=%s, p_age=%s, p_docname=%s, p_gender=%s WHERE p_id = %s", 
                             (p_name, p_dob, p_age, p_docname, p_gender, id))
                connection.commit()
                flash('Patient Edited','success')
                return redirect(url_for('patients'))
            return render_template('edit_patient.html',form=form)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return redirect(url_for('patients'))
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return redirect(url_for('patients'))

@app.route('/delete_patient/<string:id>', methods=['POST'])
@is_logged_in
@is_physician_in
def delete_patient(id):
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor()
            cursor.execute("DELETE FROM patients WHERE p_id=%s", (id,))
            connection.commit()
            flash('Patient Deleted','success')
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
    return redirect(url_for('patients'))

@app.route('/history/<string:id>')
@is_logged_in
@is_physician_in
def mal_history(id):
    user_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM patients WHERE p_id=%s AND user_id=%s", (id, user_id))
            data = cursor.fetchone()

            if data is None:
                flash("No Such Record Exists",'danger')
                return redirect(url_for('classify'))
            
            cursor.execute("SELECT * FROM disease WHERE patient_id=%s ORDER BY create_date DESC", (id,))
            history = cursor.fetchall()

            if history:
                return render_template('mal_history.html', history=history)
            else:
                msg = "No History Found"
                return render_template('mal_history.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return redirect(url_for('classify'))
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return redirect(url_for('classify'))

@app.route('/classify')
@is_logged_in
@is_physician_in
def classify():
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            id = session['id']
            cursor.execute("SELECT *,concat('P21-',lpad(p_id,5,'0')) as p_id2 FROM patients WHERE user_id=%s", (id,))
            patients = cursor.fetchall()

            if patients:
                return render_template('classify.html', patients=patients)
            else:
                msg = "No Patients Found"
                return render_template('classify.html', msg=msg)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('classify.html')
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('classify.html')

@app.route('/classify_image/<string:id>',methods = ['GET', 'POST'])
@is_logged_in
@is_physician_in
def classify_image(id):
    user_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM patients WHERE p_id=%s AND user_id=%s", (id, user_id))
            data = cursor.fetchone()

            if data is None:
                flash("No Such Record Exists",'danger')
                return redirect(url_for('classify'))

            full_filename = 'img/no_image.PNG'

            if request.method == "GET":
                return render_template("classify_image.html", full_filename=full_filename)

            if request.method == "POST":
                image_upload = request.files['image_upload']
                if not(image_upload):
                    flash('No File Uploaded','danger')
                    return render_template('classify_image.html',full_filename=full_filename)
                elif not(allowed_file(image_upload.filename)):
                    flash('Only .png, .jpg, .jpeg file extensions allowed','danger')
                    return render_template('classify_image.html',full_filename=full_filename)
                else:
                    letters = string.ascii_lowercase
                    name = ''.join(random.choice(letters) for i in range(10)) + '.png'
                    full_filename = 'img/uploads/' + name
                    imagename = image_upload.filename
                    image = Image.open(image_upload)
                    image = image.resize((128,128))
                    img_path = os.path.join(app.config['INITIAL_FILE_UPLOADS'], name)
                    image.save(img_path)
                    pred, prob = predict_label(img_path)
                    cursor.execute("INSERT INTO disease(patient_id,disease_name,image) VALUES(%s,%s,%s)", 
                                 (id, pred, img_path))
                    connection.commit()
                    disease_id = cursor.lastrowid
                    app.logger.info(disease_id)
                    return render_template('classify_image.html', full_filename=full_filename, pred=pred, prob=prob, disease_id=disease_id)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return redirect(url_for('classify'))
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return redirect(url_for('classify'))

@app.route('/mal_pdf/<string:id>')
@is_logged_in
@is_physician_in
def mal_pdf(id):
    user_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT * FROM disease WHERE disease_id=%s", (id,))
            data = cursor.fetchone()

            if data is None:
                flash("No Such Record Exists",'danger')
                return redirect(url_for('classify'))

            cursor.execute("SELECT *,concat('22-',lpad(patients.p_id,4,'0')) as p_id2 FROM patients INNER JOIN disease ON patients.p_id=disease.patient_id WHERE disease.disease_id=%s AND patients.user_id=%s", (id, user_id))
            data = cursor.fetchone()

            if data is None:
                flash("No Such Record Exists",'danger')
                return redirect(url_for('classify'))

            id = data['p_id2']
            create_date = data['create_date']
            name = data['p_name']
            dob = data['p_dob']
            age = data['p_age']
            gender = data['p_gender']
            disease_name = data['disease_name']

            src = os.path.dirname(os.path.abspath(__file__))+'/'+data['image']
            app.logger.info(src)

            rendered = render_template('mal_pdf.html',
                                    id=id,
                                    full_filename=src,
                                    name=name,
                                    dob=dob,
                                    age=age,
                                    gender=gender,
                                    time_added=create_date,
                                    pred=disease_name)
            
            # Generate PDF with WeasyPrint
            pdf = HTML(string=rendered).write_pdf()
            
            response = make_response(pdf)
            response.headers['Content-Type'] = 'application/pdf'
            response.headers['Content-Disposition'] = 'inline; filename=report.pdf'
            return response
            
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return redirect(url_for('classify'))
        finally:
            cursor.close()
            connection.close()
            
            
class GenerateLabReport(Form):
    patient = SelectField(u'Patient Name',coerce = int)
    report_date = SelectField(u'Report Date',coerce = int)

@app.route('/lab_reports',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def labReports():
    form = GenerateLabReport(request.form)
    doc_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            patient_result = cursor.execute("SELECT p_id,p_name FROM patients WHERE user_id=%s AND p_id in (SELECT patient_id FROM lab_reports)", (doc_id,))
            patients = cursor.fetchall()
            patientData = []

            for patient in patients:
                patientData.append((patient['p_id'], patient['p_name']))
            form.patient.choices = patientData

            if request.method == 'POST':
                patient = str(form.patient.data)
                report_date = str(request.form['report_date'])
                app.logger.info(report_date)
                return patient + " " + report_date
            return render_template('lab_reports.html',form=form)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('lab_reports.html',form=form)
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('lab_reports.html',form=form)

@app.route('/process',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def process():
    patient_id = request.form['patient']

    if patient_id:
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor(dictionary=True)
                cursor.execute("SELECT DATE_FORMAT(date,'%%Y-%%m-%%d') as report_date FROM lab_reports WHERE patient_id = %s GROUP BY report_date", (patient_id,))
                report_dates = cursor.fetchall()
                return jsonify(report_dates)
            except Error as e:
                app.logger.error(f"Database error: {e}")
                return 'error'
            finally:
                cursor.close()
                connection.close()
    return 'error'

@app.route('/lab_report_pdf',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def lab_report_pdf():
    physician_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT name from user WHERE id=%s", (physician_id,))
            data = cursor.fetchone()

            if data:
                physician_name = data['name']
            else:
                return 'No User Data Found'

            if request.method == 'POST':
                patient_id = request.form['patient']
                report_date = request.form['report_date']
                cursor.execute("SELECT * FROM (((lab_reports INNER JOIN patients ON p_id = patient_id) INNER JOIN tests_under ON lab_reports.test_id = tests_under.id) INNER JOIN lab_tests ON tests_under.test_id = lab_tests.Id) WHERE DATE_FORMAT(lab_reports.date,'%%Y-%%m-%%d')=%s AND lab_reports.patient_id=%s ORDER BY lab_tests.test_name", (report_date, patient_id))
                report_details = cursor.fetchall()

                if report_details:
                    report_data = {}

                    for info in report_details:
                        report_data[info['test_name']] = {'TEST':[],'RESULT':[],'UNIT':[],'UPPER_LIMIT':[],'LOWER_LIMIT':[]}

                    for info in report_details:
                        report_data[info['test_name']]['TEST'].append(info['test_name'])
                        report_data[info['test_name']]['RESULT'].append(info['test_value'])
                        report_data[info['test_name']]['UNIT'].append(info['unit'])
                        report_data[info['test_name']]['UPPER_LIMIT'].append(info['upper_limit'])
                        report_data[info['test_name']]['LOWER_LIMIT'].append(info['lower_limit'])
                        report_data[info['test_name']]['LENGTH'] = len(report_data[info['test_name']]['TEST'])

                    rendered = render_template('lab_report_pdf.html',report_details=report_details,report_date=report_date,physician_name=physician_name,report_data=report_data)
                    options = {
                        "enable-local-file-access": None
                    }
                    pdf = pdfkit.from_string(rendered,False,options=options)
                    response = make_response(pdf)
                    response.headers['Content-Type'] = 'application/pdf'
                    response.headers['Content-Disposition'] = 'inline; lab_report.pdf'
                    return response
                else:
                    msg = "No User Data Found"
                    return msg
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return "Error generating report"
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return "Database connection error"

class labTest(Form):
    test_name = StringField(label='Test name',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^[a-zA-Z ]*$",message="Only alphabets and spaces are allowed")])
    code = StringField(label='code',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^[a-zA-Z ]*$",message="Only alphabets and spaces are allowed")])
    submit = SubmitField(label="Submit")

class TestUnder(Form):
    test_name = StringField(label='Test name',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^[a-zA-Z ]*$",message="Only alphabets and spaces are allowed")])
    lower_limit = StringField(label='Lower limit',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^([0-9]+[.]?[0-9]*)$",message="Only positive numeric or decimal values allowed")])
    upper_limit = StringField(label='Upper limit',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^([0-9]+[.]?[0-9]*)$",message="Only positive numeric or decimal values allowed")])
    unit = StringField(label='Unit',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^[a-zA-Z/%]*$",message="Only alphabets and some special characters allowed (/,%)")])
    unit_price = StringField(label='Unit price',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^([0-9]+[.]?[0-9]*)$",message="Only numeric or decimal values allowed")])
    taxes = StringField(label='Taxes',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^([0-9]+[.]?[0-9]*)$",message="Only numeric or decimal values allowed")])

@app.route('/test_under/<string:id>',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def testUnder(id):
    form = TestUnder(request.form)

    if request.method == 'POST' and form.validate():
        test_name = form.test_name.data
        lower_limit = form.lower_limit.data
        upper_limit = form.upper_limit.data
        unit = form.unit.data
        unit_price = form.unit_price.data
        taxes = form.taxes.data
        
        connection = get_db_connection()
        if connection:
            try:
                cursor = connection.cursor()
                cursor.execute("INSERT INTO tests_under(test_name,test_id,lower_limit,upper_limit,unit,unit_price,taxes) VALUES(%s, %s, %s, %s, %s, %s, %s)",
                             (test_name, id, lower_limit, upper_limit, unit, unit_price, taxes))
                connection.commit()
                flash('Test Under Category Created', 'success')
                return redirect(url_for('testUnder',id=id))
            except Error as e:
                flash("Database error occurred", 'danger')
                app.logger.error(f"Database error: {e}")
            finally:
                cursor.close()
                connection.close()
        else:
            flash("Database connection error", 'danger')

    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT test_name from lab_tests WHERE id = %s", (id,))
            data = cursor.fetchone()
            lab_test = data['test_name']
            cursor.execute("SELECT * FROM tests_under WHERE test_id=%s", (id,))
            tests = cursor.fetchall()

            if tests:
                return render_template('test_under.html', tests=tests, form=form, lab_test=lab_test)
            else:
                msg = 'No Tests Under Category Found'
                return render_template('test_under.html', msg=msg, form=form, lab_test=lab_test)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('test_under.html', form=form)
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('test_under.html', form=form)

class LabReport(Form):
    patient = SelectField(u'Patient',coerce = int)
    test_value = StringField(label='Test Value',validators=[DataRequired(),validators.Length(min=1),validators.Regexp(regex="^([0-9]+[.]?[0-9]*)$",message="Only numeric or decimal values allowed")])

@app.route('/add_lab_report/<string:id>',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def addLabReport(id):
    form = LabReport(request.form)
    doc_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT p_id,p_name FROM patients WHERE user_id=%s", (doc_id,))
            patients = cursor.fetchall()
            patientData = []

            for patient in patients:
                patientData.append((patient['p_id'], patient['p_name']))
            form.patient.choices = patientData

            if request.method == 'POST' and form.validate():
                patient_id = form.patient.data
                test_value = form.test_value.data
                cursor.execute("INSERT INTO lab_reports(test_id,patient_id,test_value) VALUES(%s,%s,%s)", (id, patient_id, test_value))
                connection.commit()
                flash('Report Added','success')
                return redirect(url_for('addLabReport',id=id))

            cursor.execute("SELECT lab_tests.test_name as test_type_name,lab_tests.Id as type_id, tests_under.test_name as test_name FROM lab_tests INNER JOIN tests_under ON lab_tests.Id=tests_under.test_id WHERE tests_under.id=%s", (id,))
            data = cursor.fetchone()
            test_data = data
            cursor.execute("SELECT p_id,p_name FROM patients WHERE user_id=%s", (doc_id,))

            if patients:
                return render_template('add_lab_report.html', test_data=test_data, form=form)
            else:
                msg = "No Patients Found"
                return render_template('add_lab_report.html', msg=msg, form=form)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('add_lab_report.html', form=form)
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('add_lab_report.html', form=form)

class LabRequest(Form):
    patient = SelectField(u'Patient',coerce = int)
    request_date = DateTimeLocalField('Request Date',format='%Y-%m-%dT%H:%M',validators=[DataRequired()])
    urgency = SelectField(u'Urgency Level',choices = [('Normal','Normal'),('High','High'),('Very High','Very High')])

@app.route('/add_lab_request/<string:id>',methods=['GET','POST'])
@is_logged_in
@is_physician_in
def addLabRequest(id):
    form = LabRequest(request.form)
    doc_id = session['id']
    connection = get_db_connection()
    if connection:
        try:
            cursor = connection.cursor(dictionary=True)
            cursor.execute("SELECT p_id,p_name FROM patients WHERE user_id=%s", (doc_id,))
            patients = cursor.fetchall()
            patientData = []

            for patient in patients:
                patientData.append((patient['p_id'], patient['p_name']))
            form.patient.choices = patientData

            if request.method == 'POST' and form.validate():
                request_date = form.request_date.data.strftime("%Y-%m-%d %H:%M:00")
                patient_id = form.patient.data
                urgency_level = form.urgency.data
                cursor.execute("INSERT INTO lab_requests(test_id,patient_id,urgency_level,request_date) VALUES(%s,%s,%s,%s)", 
                             (id, patient_id, urgency_level, request_date))
                connection.commit()
                flash('Request Added','success')
                return redirect(url_for('addLabRequest',id=id))

            cursor.execute("SELECT lab_tests.test_name as test_type_name,lab_tests.Id as type_id, tests_under.test_name as test_name FROM lab_tests INNER JOIN tests_under ON lab_tests.Id=tests_under.test_id WHERE tests_under.id=%s", (id,))
            data = cursor.fetchone()
            test_data = data

            if patients:
                return render_template('add_lab_request.html', test_data=test_data, form=form)
            else:
                msg = "No Patients Found"
                return render_template('add_lab_request.html', msg=msg, form=form)
        except Error as e:
            flash("Database error occurred", 'danger')
            app.logger.error(f"Database error: {e}")
            return render_template('add_lab_request.html', form=form)
        finally:
            cursor.close()
            connection.close()
    else:
        flash("Database connection error", 'danger')
        return render_template('add_lab_request.html', form=form)

if __name__ == "__main__":
    app.secret_key='secret123'
    app.run(debug=True)