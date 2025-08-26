from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import mysql.connector
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from flask_bcrypt import Bcrypt
from flask_mail import Mail, Message
import random

app = Flask(__name__)
app.secret_key = 'AE54'  # 세션을 위한 비밀 키 설정
bcrypt = Bcrypt(app)

# Flask-Mail 초기화
mail = Mail(app)

# 이메일 설정
app.config['MAIL_SERVER'] = 'smtp.gmail.com'  # SMTP 서버 주소
app.config['MAIL_PORT'] = 587
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USERNAME'] = ''  # 발신 이메일
app.config['MAIL_PASSWORD'] = ''  # 이메일 비밀번호
mail.init_app(app)

# 데이터베이스 연결 설정
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password="4528",
    database="productdb"
)

cursor = db.cursor(dictionary=True)

# 댓글을 가져오는 함수
def get_comments_for_famous_person(famous_person):
    cursor.execute("SELECT c.comment, u.nick_name FROM comment c JOIN users u ON c.user_id = u.user_id WHERE c.name = %s", (famous_person,))
    return cursor.fetchall()

# 데이터 관리를 위한 클래스
class ProductRecommender:
    # 생성자: 클래스가 초기화될 때 호출됨
    def __init__(self):
        self.table_names = ['star', 'mainstream', 'highend', 'flagship']  # 사용할 데이터베이스 테이블 이름 리스트
        self.current_table = 'mainstream'  # 기본 테이블을 'mainstream'으로 설정
        self.load_products()  # 초기화 시 제품 데이터를 로드

    # 카테고리 분류 및 TF-IDF 행렬 생성 ( TF - IDF 텍스트의 키워드를 기반으로 핵심내용 추출 )
    def load_products(self):
        cursor.execute(f"SELECT * FROM {self.current_table}")  # 현재 테이블에서 모든 데이터 선택
        self.products = pd.DataFrame(cursor.fetchall())  # 데이터를 DataFrame으로 변환
        self.categories = self.products['카테고리'].unique()  # 카테고리 레이블 리스트 생성
        self.products['카테고리'] = self.products['카테고리'].fillna('')  # NaN 값을 빈 문자열로 대체
        self.tfidf = TfidfVectorizer(stop_words='english')  # TF-IDF 벡터라이저 초기화
        self.tfidf_matrix = self.tfidf.fit_transform(self.products['카테고리'])  # 카테고리 데이터를 TF-IDF 행렬로 변환
        self.cosine_sim = linear_kernel(self.tfidf_matrix, self.tfidf_matrix)  # 코사인 유사도 행렬 생성

        # => TF-IDF는 정보 검색과 텍스트 마이닝에서 널리 사용되는 가중치 조합 방법 TF-IDF는 단어의 중요도를 평가하여 문서의 특징을 나타내는 데 사용
        # => 즉 카테고리 리스트를 기준으로 잡고 가는것

    # 테이블 선택 업데이트 및 데이터 로드 ( 프로선수, 방송인 선택영역 )
    def update_table_selection(self, table_index):
        self.current_table = self.table_names[table_index]  # 선택된 테이블 이름으로 업데이트
        self.load_products()  # 새 테이블에서 데이터 로드

    # 제품 추천 로직
    def get_recommendations(self, category, num_recommendations=8):
        exact_match_indices = self.products[self.products['카테고리'] == category].index.tolist()  # 정확히 일치하는 카테고리 인덱스 리스트
        related_indices = self.products[self.products['카테고리'].str.contains(category)].index.tolist()  # 카테고리를 포함하는 인덱스 리스트
        final_indices = list(dict.fromkeys(exact_match_indices + related_indices))  # 중복 제거 및 인덱스 결합
        final_indices = final_indices[:num_recommendations]  # 추천 수 제한
        result = self.products.loc[final_indices][['제품', '설명']]  # 추천 제품과 설명을 포함한 DataFrame 생성
        return result.to_dict(orient='records')  # 결과를 딕셔너리 형태로 반환

# ProductRecommender 인스턴스 생성
recommender = ProductRecommender()

# 회원가입 페이지 라우트
@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        name = request.form['name']
        nick_name = request.form['nick_name']
        user_id = request.form['id']
        password = request.form['password']
        email = request.form['email']
        admin_user = 0  # 기본적으로 일반 유저로 설정

        # 비밀번호 해시화 ( 현재 사용하지 않음 )
        hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

        # 중복 확인 쿼리
        cursor.execute("SELECT * FROM users WHERE id = %s OR email = %s", (user_id, email))
        existing_user = cursor.fetchone()
        
        if existing_user:
            alert_message = "[회원가입 실패] 아이디 또는 이메일이 이미 사용 중입니다."
            return render_template('signup.html', alert_message=alert_message)
        
        # 사용자 정보를 데이터베이스에 삽입
        cursor.execute("""
            INSERT INTO users (name, nick_name, id, password, email, admin_user)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (name, nick_name, user_id, hashed_password, email, admin_user))
        db.commit()

        return redirect(url_for('index'))
    return render_template('signup.html')

# 로그인 페이지 라우트
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user_id = request.form['id']
        password = request.form['password']

        # 사용자 정보 조회
        cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
        user = cursor.fetchone()

        # 사용자 검증
        if user and bcrypt.check_password_hash(user['password'], password): # 사용자 입력 PW 비교
            session['user_id'] = user['user_id']
            session['id'] = user['id']
            session['user_name'] = user['name']
            session['user_nick_name'] = user['nick_name']
            session['user_email'] = user['email']
            session['admin_user'] = user['admin_user']
            return redirect(url_for('index'))
        else:
            return render_template('login.html', alert_message="[로그인 실패] 아이디나 비밀번호가 잘못되었습니다.")
    return render_template('login.html')

# 로그아웃 라우트
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# PW변경
@app.route('/pw_change', methods=['POST'])
def pw_change():
    if request.method == 'POST':
        new_pw = request.form['new_pw']
        new_pw_chk = request.form['new_pw_chk']

        if new_pw == new_pw_chk:
            # 새 비밀번호 해시화
            hashed_new_pw = bcrypt.generate_password_hash(new_pw).decode('utf-8')

            # 해시화된 비밀번호로 업데이트
            cursor = db.cursor()  # db 연결 커서 생성
            cursor.execute("UPDATE users SET password = %s WHERE id = %s", (hashed_new_pw, session['id']))
            db.commit()  # 변경 사항 커밋
            cursor.close()  # 커서 닫기
            return render_template('Mypage.html', alert_message="비밀번호 변경에 성공했습니다.")
        else:
            return render_template('Mypage.html', alert_message="[비밀번호 변경 실패] PW를 다르게 입력했습니다.")
    return render_template('Mypage.html')

# PW변경 ( 이메일 기준 )
@app.route('/pw_change_email', methods=['POST'])
def pw_change_email():
    if request.method == 'POST':
        new_pw = request.form['new_pw']
        new_pw_chk = request.form['new_pw_chk']

        if new_pw == new_pw_chk:
            # 새 비밀번호 해시화
            hashed_new_pw = bcrypt.generate_password_hash(new_pw).decode('utf-8')

            # 해시화된 비밀번호로 업데이트
            cursor = db.cursor()  # db 연결 커서 생성
            cursor.execute("UPDATE users SET password = %s WHERE email = %s", (hashed_new_pw, session['email']))
            db.commit()  # 변경 사항 커밋
            cursor.close()  # 커서 닫기
            session.pop('email')
            return render_template('home.html', alert_message="비밀번호 변경에 성공했습니다.")
        else:
            return render_template('account_result_pw.html', alert_message="[비밀번호 변경 실패] PW를 다르게 입력했습니다.")
    return render_template('home.html')

# ID PW 찾기 페이지 라우트
@app.route('/findAccount', methods=['GET', 'POST'])
def findAccount():
    return render_template('findAccount.html')

# ID / PW 찾는 로직
@app.route('/find_id', methods=['POST'])
def find_id():
    email = request.form['email']

    # 데이터베이스에서 이메일 확인
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if user:
        random_number = str(random.randint(10000, 99999))  # 랜덤 5자리 숫자 생성

        # 이메일 전송
        msg = Message('장비좀봐줄래? ID 분실 확인 메일', sender='장비좀봐줄래?', recipients=[email])
        msg.body = f'인증번호: {random_number} 를 인증확인 창에 기입해 주세요.'
        mail.send(msg)

        # 세션이나 다른 방법으로 랜덤 숫자를 저장
        session['verification_code'] = random_number
        session['email'] = email  # 추가: 이메일도 세션에 저장
        return render_template('verify_code.html', action='find_id')
    
    return render_template('findAccount.html', alert_message = "해당 이메일은 존재하지 않는 이메일입니다.")

@app.route('/find_pw', methods=['POST'])
def find_pw():
    email = request.form['email']

    # 데이터베이스에서 이메일 확인
    cursor.execute("SELECT * FROM users WHERE email = %s", (email,))
    user = cursor.fetchone()

    if user:
        random_number = str(random.randint(10000, 99999))  # 랜덤 5자리 숫자 생성

        # 이메일 전송
        msg = Message('장비좀봐줄래? PW 분실 확인 메일', sender='장비좀봐줄래?', recipients=[email])
        msg.body = f'인증번호: {random_number} 를 인증확인 창에 기입해 주세요.'
        mail.send(msg)

        # 세션이나 다른 방법으로 랜덤 숫자를 저장
        session['verification_code'] = random_number
        session['email'] = email  # 추가: 이메일도 세션에 저장
        return render_template('verify_code.html', action='find_pw')

    return render_template('findAccount.html', alert_message = "해당 이메일은 존재하지 않는 이메일입니다.")

# 입력된 코드 확인 및 ID/PW 반환 페이지 라우트
@app.route('/verify_codes', methods=['POST'])
def verify_codes():
    input_code = request.form['code']
    action = request.form['action']

    if input_code == session.get('verification_code'):
        if action == 'find_id':
            cursor.execute("SELECT id FROM users WHERE email = %s", (session.get('email'),))
            user = cursor.fetchone()
            return render_template('account_result.html', find_account_id = '회원님의 ID 는 ' + user['id'] + ' 입니다.')# ID 반환
            #return f"Your ID is: {user['id']}"  # ID 반환
        elif action == 'find_pw':
            cursor.execute("SELECT password FROM users WHERE email = %s", (session.get('email'),))
            user = cursor.fetchone()
            return render_template('account_result_pw.html', find_account_id = '비밀번호 변경')

    return "잘못된 접근입니다."

# 내 정보
@app.route('/mypage')
def mypage():
    return render_template('Mypage.html')

# 메인 페이지 라우트
@app.route('/')
def index():
    return render_template('home.html')

# League of Legends 페이지 라우트
@app.route('/LOL')
def league():
    return render_template('League_Of_Legends.html')

# PUBG 페이지 라우트
@app.route('/PUBG')
def PUBG():
    return render_template('PUBG.html')

# Overwatch 페이지 라우트
@app.route('/Overwatch')
def Overwatch():
    return render_template('Overwatch.html')

# CounterStrike2 페이지 라우트
@app.route('/CS2')
def CounterStrike2():
    return render_template('CounterStrike2.html')

# CounterStrike2 페이지 라우트
@app.route('/SA')
def SA():
    return render_template('Suddenattack.html')

# CounterStrike2 페이지 라우트
@app.route('/valo')
def Valo():
    return render_template('Valorant.html')

# index.html 호출 시 유명인의 제품 정보를 가져오는 기능 추가
@app.route('/index')
def index_with_star():
    famous_person = request.args.get('name')
    table_index = int(request.args.get('table_index', 0))  # 기본값은 0으로 설정

    # 유명인 정보 가져오기
    cursor.execute(f"SELECT * FROM Star WHERE name = '{famous_person}'")
    famous_person_data = cursor.fetchone()
    
    # 댓글 가져오기
    comments = get_comments_for_famous_person(famous_person)

    return render_template('index.html', famous_person=famous_person, famous_person_data=famous_person_data, categories=recommender.categories, comments=comments)

# 이미지 선택값 받아오기
@app.route('/update_data_select', methods=['POST'])
def update_data_select():
    data = request.get_json()
    table_index = int(data.get('value'))
    recommender.update_table_selection(table_index)
    return jsonify({'status': 'success', 'message': 'Table selection updated successfully.'})

# index.html 의 form action 태그의 내용
@app.route('/recommend', methods=['POST'])
def recommend():
    category = request.form['category']
    recommended_products = recommender.get_recommendations(category)
    
    # 유명인의 제품 정보를 가져오는 로직 추가
    famous_person = request.args.get('name')
    famous_person_data = None  # 기본값으로 설정
    comments = []
    if famous_person:
        cursor.execute(f"SELECT * FROM Star WHERE name = '{famous_person}'")
        famous_person_data = cursor.fetchone()
        
        # 댓글 가져오기
        comments = get_comments_for_famous_person(famous_person)
    
    return render_template('index.html', famous_person=famous_person, famous_person_data=famous_person_data, product_title=category, recommended_products=recommended_products, categories=recommender.categories, comments=comments)

# 댓글 저장 라우트
@app.route('/add_comment', methods=['POST'])
def add_comment():
    if 'user_id' not in session:
        return jsonify({'error': '로그인이 필요합니다.'}), 401
    
    famous_person = request.form['famous_person']
    comment = request.form['comment']
    user_id = session.get('user_id')  # 세션에 로그인된 유저의 고유번호

    if user_id and famous_person and comment:
        cursor.execute("""
            INSERT INTO comment (name, user_id, comment)
            VALUES (%s, %s, %s)
        """, (famous_person, user_id, comment))
        db.commit()

    return jsonify({'success': '댓글이 추가되었습니다.'}), 200

# 에러 관련
@app.errorhandler(Exception)
def handle_exception(e):
    return render_template('error.html', error_message="알 수 없는 오류가 발생했습니다."), 500


# 서버 실행
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0') # 배포버전에선 debug=false 로 올린다.