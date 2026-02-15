from flask import Flask, render_template, redirect, url_for, request, flash, session, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import os
import click
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from flask_mail import Mail, Message
from dotenv import load_dotenv

load_dotenv()

from extensions import db, migrate
from models import (
    User, Student, Course, Group, Lecture, Employee, Department,
    Material, Test, Question, Option, Attempt, AttemptAnswer,
    AIQuestion, AIAnswer, AIResult, HomeworkSubmission
)
from translations import DEFAULT_LANG, LANGUAGES, current_lang, translate_html


app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY') or os.urandom(24).hex()

# Absolute paths to avoid CWD confusion
BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DB_PATH = os.path.join(BASE_DIR, 'database.db')

# PostgreSQL connection (Render uses DATABASE_URL)
def _normalize_db_url(url: str) -> str:
    if url.startswith('postgres://'):
        url = 'postgresql://' + url[len('postgres://'):]
    if 'sslmode=' not in url and url.startswith('postgresql://'):
        url += '?sslmode=require'
    return url

db_url = os.environ.get('DATABASE_URL')
if db_url:
    app.config['SQLALCHEMY_DATABASE_URI'] = _normalize_db_url(db_url)
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql+psycopg2://lms_user:1234@localhost:5432/lms_db"

# Avoid stale SSL connections on managed Postgres
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Uploads
app.config['UPLOAD_FOLDER'] = os.path.join(BASE_DIR, 'uploads')
TEST_IMAGE_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'test_images')
HOMEWORK_UPLOAD_FOLDER = os.path.join(app.config['UPLOAD_FOLDER'], 'homework')
ALLOWED_EXTENSIONS = {"pdf", "doc", "docx", "ppt", "pptx", "zip", "rar", "7z", "mp4", "txt"}
ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

# Email (Gmail SMTP)
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', '587'))
app.config['MAIL_USE_TLS'] = os.environ.get('MAIL_USE_TLS', '1') == '1'
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER') or app.config['MAIL_USERNAME']
app.config['APP_PUBLIC_URL'] = os.environ.get('APP_PUBLIC_URL')

mail = Mail(app)

def _current_lang():
    return current_lang()


def _translate_html(text: str) -> str:
    return translate_html(text)

# ENT combinations and explanations (deterministic rules)
ENT_COMBINATIONS = {
    "math_inf": {
        "title": "Математика – Информатика",
        "description": "IT, программирование, анализ данных и кибербезопасность.",
        "careers": ["Разработчик ПО", "Data analyst", "Инженер-программист", "QA-инженер"],
        "faculties": ["Информационные технологии", "Компьютерные науки", "Кибербезопасность", "Информационные системы"],
        "specialties": [
            {"code": "B057", "title": "Ақпараттық технологиялар"},
            {"code": "B058", "title": "Ақпараттық қауіпсіздік"},
            {"code": "B157", "title": "Математикалық және компьютерлік модельдеу"},
            {"code": "B158", "title": "Криптология"},
            {"code": "B011", "title": "Информатика мұғалімдерін даярлау"}
        ],
        "best_specialty": {"code": "B057", "title": "Ақпараттық технологиялар"}
    },
    "math_phys": {
        "title": "Математика – Физика",
        "description": "Инженерия, техника, энергетика и прикладные технологии.",
        "careers": ["Инженер", "Инженер-исследователь", "Техспециалист", "Системный инженер"],
        "faculties": ["Инженерия", "Физика", "Энергетика", "Технологии и строительство"],
        "specialties": [
            {"code": "B009", "title": "Математика мұғалімдерін даярлау"},
            {"code": "B010", "title": "Физика мұғалімдерін даярлау"},
            {"code": "B054", "title": "Физика"},
            {"code": "B055", "title": "Математика және статистика"},
            {"code": "B056", "title": "Механика"},
            {"code": "B059", "title": "Коммуникациялар және коммуникациялық технологиялар"},
            {"code": "B061", "title": "Материалтану және технологиялар"},
            {"code": "B062", "title": "Электр техникасы және энергетика"},
            {"code": "B063", "title": "Электр техникасы және автоматтандыру"},
            {"code": "B064", "title": "Механика және метал өңдеу"},
            {"code": "B065", "title": "Автокөлік құралдары"},
            {"code": "B066", "title": "Теңіз көлігі және технологиялары"},
            {"code": "B067", "title": "Әуе көлігі және технологиялары"},
            {"code": "B069", "title": "Материалдар өндірісі (шыны, қағаз, пластик, ағаш)"},
            {"code": "B070", "title": "Тоқыма: киім, аяқ киім және былғары бұйымдары"},
            {"code": "B071", "title": "Тау-кен ісі және пайдалы қазбаларды өндіру"},
            {"code": "B074", "title": "Қала құрылысы, құрылыс жұмыстары және азаматтық құрылыс"},
            {"code": "B076", "title": "Стандарттау, сертификаттау және метрология (сала бойынша)"},
            {"code": "B082", "title": "Су ресурстары және суды пайдалану"},
            {"code": "B094", "title": "Санитарлық-профилактикалық іс-шаралар"},
            {"code": "B120", "title": "Кәсіптік оқыту педагогтарын даярлау"},
            {"code": "B126", "title": "Көлік құрылысы"},
            {"code": "B161", "title": "Материалдық инженерия"},
            {"code": "B162", "title": "Жылу энергетикасы"},
            {"code": "B165", "title": "Магистральды желілер және инфрақұрылым"},
            {"code": "B166", "title": "Көліктік имараттар"},
            {"code": "B167", "title": "Ұшатын аппараттар мен қозғалтқыштарды ұшуда пайдалану"},
            {"code": "B171", "title": "Металлургия"},
            {"code": "B172", "title": "Материалды қысыммен өңдеу"},
            {"code": "B173", "title": "Гидромелиорация"},
            {"code": "B175", "title": "Сумен қамтамасыз ету және суды бұру"},
            {"code": "B176", "title": "Гидротехникалық құрылыс және су ресурстарын басқару"},
            {"code": "B183", "title": "Агроинженерия"},
            {"code": "B265", "title": "Темір жол көлігі және технология"}
        ],
        "best_specialty": {"code": "B062", "title": "Электр техникасы және энергетика"}
    },
    "math_geo": {
        "title": "Математика – География",
        "description": "Экономика, управление, логистика и территориальная аналитика.",
        "careers": ["Экономист-аналитик", "Логист", "Финансист", "Менеджер"],
        "faculties": ["Экономика и управление", "Логистика", "ГИС и картография", "Градостроительство"],
        "specialties": [
            {"code": "B038", "title": "Әлеуметтану"},
            {"code": "B044", "title": "Менеджмент және басқару"},
            {"code": "B045", "title": "Аудит және салық салу"},
            {"code": "B046", "title": "Қаржы, экономика, банк және сақтандыру ісі"},
            {"code": "B047", "title": "Маркетинг және жарнама"},
            {"code": "B048", "title": "Еңбек дағдылары"},
            {"code": "B052", "title": "Жер туралы ғылым"},
            {"code": "B075", "title": "Кадастр және жерге орналастыру"},
            {"code": "B095", "title": "Көлік қызметтері"},
            {"code": "B145", "title": "Мемлекеттік аудит"}
        ],
        "best_specialty": {"code": "B046", "title": "Қаржы, экономика, банк және сақтандыру ісі"}
    },
    "bio_chem": {
        "title": "Биология – Химия",
        "description": "Медицина, биотехнологии, фармацевтика и лабораторные исследования.",
        "careers": ["Врач", "Фармацевт", "Биотехнолог", "Лабораторный аналитик"],
        "faculties": ["Медицина", "Фармация", "Биотехнологии", "Химическая технология"],
        "specialties": [
            {"code": "BM086", "title": "Медицина"},
            {"code": "BM087", "title": "Стоматология"},
            {"code": "BM088", "title": "Педиатрия"},
            {"code": "BM089", "title": "Медициналық-профилактикалық іс"},
            {"code": "B083", "title": "Ветеринария"},
            {"code": "B084", "title": "Мейіргер ісі"},
            {"code": "B085", "title": "Фармация"},
            {"code": "B089", "title": "Қоғамдық денсаулық сақтау"},
            {"code": "B050", "title": "Биологиялық және сабақтас ғылымдар (Биотехнология)"},
            {"code": "B053", "title": "Химия"},
            {"code": "B068", "title": "Азық-түлік өнімдерінің өндірісі"},
            {"code": "B072", "title": "Фармацевтикалық өндіріс технологиясы"},
            {"code": "B077", "title": "Өсімдік шаруашылығы"},
            {"code": "B078", "title": "Мал шаруашылығы"},
            {"code": "B080", "title": "Балық шаруашылығы"},
            {"code": "B012", "title": "Химия мұғалімдерін даярлау"},
            {"code": "B013", "title": "Биология мұғалімдерін даярлау"}
        ],
        "best_specialty": {"code": "BM086", "title": "Медицина"}
    },
    "bio_geo": {
        "title": "Биология – География",
        "description": "Экология, социальная сфера, педагогика и природные ресурсы.",
        "careers": ["Эколог", "Психолог", "Педагог", "Социальный работник"],
        "faculties": ["Экология", "Педагогика", "Социальные науки", "Природопользование"],
        "specialties": [
            {"code": "B001", "title": "Педагогика және психология"},
            {"code": "B002", "title": "Мектепке дейінгі оқыту және тәрбиелеу"},
            {"code": "B003", "title": "Бастауышта оқыту педагогикасы мен әдістемесі"},
            {"code": "B019", "title": "Әлеуметтік педагогтарды даярлау"},
            {"code": "B020", "title": "Арнайы педагогика (Дефектология)"},
            {"code": "B041", "title": "Психология"},
            {"code": "B051", "title": "Қоршаған орта"},
            {"code": "B079", "title": "Орман шаруашылығы"},
            {"code": "B090", "title": "Әлеуметтік жұмыс"}
        ],
        "best_specialty": {"code": "B041", "title": "Психология"}
    },
    "chem_phys": {
        "title": "Химия – Физика",
        "description": "Химическая инженерия, материалы и промышленные процессы.",
        "careers": ["Инженер-химик", "Технолог", "Материаловед"],
        "faculties": ["Химическая технология", "Материаловедение", "Инженерия"],
        "specialties": [
            {"code": "B060", "title": "Химиялық инженерия және процестер"}
        ],
        "best_specialty": {"code": "B060", "title": "Химиялық инженерия және процестер"}
    },
    "geo_foreign": {
        "title": "География – Шет тілі",
        "description": "Туризм, сервис и международная экономика.",
        "careers": ["Специалист по туризму", "Менеджер сервиса", "Экономист", "Логист"],
        "faculties": ["Туризм", "Сервис", "Международная экономика", "Логистика"],
        "specialties": [
            {"code": "B091", "title": "Туризм"},
            {"code": "B093", "title": "Мейрамхана ісі және мейрамхана бизнесі"},
            {"code": "B141", "title": "Халықаралық экономикалық қатынастар"}
        ],
        "best_specialty": {"code": "B141", "title": "Халықаралық экономикалық қатынастар"}
    },
    "geo_hist": {
        "title": "Дж. тарихы – География",
        "description": "Гуманитарные дисциплины, история и региональные исследования.",
        "careers": ["Историк", "Учитель", "Геоаналитик", "Исследователь"],
        "faculties": ["История", "География", "Педагогика", "Регионоведение"],
        "specialties": [
            {"code": "B008", "title": "Құқық және экономика негіздері мұғалімдерін даярлау"},
            {"code": "B014", "title": "География мұғалімдерін даярлау"},
            {"code": "B015", "title": "Гуманитарлық пәндер мұғалімдерін даярлау"},
            {"code": "B032", "title": "Философия және этика"},
            {"code": "B034", "title": "Тарих"},
            {"code": "B134", "title": "Археология және этнология"}
        ],
        "best_specialty": {"code": "B034", "title": "Тарих"}
    },
    "hist_law": {
        "title": "Дж. тарихы – Құқық негіздері",
        "description": "Юриспруденция, госуправление и правовая экспертиза.",
        "careers": ["Юрист", "Госслужащий", "Правовед"],
        "faculties": ["Юриспруденция", "Госуправление", "Политология"],
        "specialties": [
            {"code": "B049", "title": "Құқық"}
        ],
        "best_specialty": {"code": "B049", "title": "Құқық"}
    },
    "foreign_hist": {
        "title": "Шет тілі – Дж. тарихы",
        "description": "Языки, международные отношения и культурные исследования.",
        "careers": ["Переводчик", "Дипломат", "Менеджер проектов", "Лингвист"],
        "faculties": ["Переводческое дело", "Лингвистика", "Международные отношения", "Регионоведение"],
        "specialties": [
            {"code": "B018", "title": "Шет тілі мұғалімдерін даярлау"},
            {"code": "B035", "title": "Түркітану"},
            {"code": "B036", "title": "Аударма ісі"},
            {"code": "B039", "title": "Мәдениеттану"},
            {"code": "B040", "title": "Саясаттану"},
            {"code": "B135", "title": "Шығыстану"},
            {"code": "B140", "title": "Халықаралық қатынастар және дипломатия"},
            {"code": "B234", "title": "Музей ісі және ескерткіштерді қорғау"}
        ],
        "best_specialty": {"code": "B140", "title": "Халықаралық қатынастар және дипломатия"}
    },
    "kaz_lit": {
        "title": "Қаз. тілі – Қаз. әдебиеті",
        "description": "Филология, преподавание, редактура и работа с текстами.",
        "careers": ["Филолог", "Учитель", "Редактор", "Журналист"],
        "faculties": ["Филология", "Педагогика", "Журналистика", "Литературоведение"],
        "specialties": [
            {"code": "B016", "title": "Қазақ тілі мен әдебиеті мұғалімдерін даярлау"},
            {"code": "B037", "title": "Филология"},
            {"code": "B043", "title": "Кітапхана ісі, ақпараттарды өңдеу және мұрағат ісі"}
        ],
        "best_specialty": {"code": "B016", "title": "Қазақ тілі мен әдебиеті мұғалімдерін даярлау"}
    },
    "rus_lit": {
        "title": "Орыс тілі – Орыс әдебиеті",
        "description": "Филология, преподавание и медиа-направления.",
        "careers": ["Филолог", "Учитель", "Редактор", "Корректор"],
        "faculties": ["Филология", "Педагогика", "Журналистика", "Литературоведение"],
        "specialties": [
            {"code": "B017", "title": "Орыс тілі мен әдебиеті мұғалімдерін даярлау"},
            {"code": "B037", "title": "Филология"},
            {"code": "B043", "title": "Кітапхана ісі, ақпараттарды өңдеу және мұрағат ісі"}
        ],
        "best_specialty": {"code": "B017", "title": "Орыс тілі мен әдебиеті мұғалімдерін даярлау"}
    },
    "creative": {
        "title": "Шығармашылық (творческий экзамен)",
        "description": "Творческие и медиа-направления, дизайн и искусство.",
        "careers": ["Дизайнер", "Архитектор", "Режиссёр", "Художник"],
        "faculties": ["Дизайн", "Архитектура", "Искусство", "Медиа и коммуникации"],
        "specialties": [
            {"code": "B073", "title": "Сәулет"},
            {"code": "B031", "title": "Сән, дизайн"},
            {"code": "B023", "title": "Режиссура, арт-менеджмент"},
            {"code": "B027", "title": "Театр өнері"},
            {"code": "B028", "title": "Хореография"},
            {"code": "B029", "title": "Аудиовизуалды өнер және медиа өндіріс"},
            {"code": "B030", "title": "Бейнелеу өнері"},
            {"code": "B042", "title": "Журналистика және репортер ісі"},
            {"code": "B142", "title": "Қоғаммен байланыс"},
            {"code": "B092", "title": "Тынығу"},
            {"code": "B098", "title": "Спорт"},
            {"code": "B021", "title": "Орындаушылық өнер"},
            {"code": "B004", "title": "Бастапқы әскери дайындық мұғалімдерін даярлау"},
            {"code": "B005", "title": "Дене шынықтыру мұғалімдерін даярлау"},
            {"code": "B006", "title": "Музыка мұғалімдерін даярлау"},
            {"code": "B007", "title": "Көркем еңбек және сызу мұғалімдерін даярлау"},
            {"code": "B033", "title": "Дінтану және теология"}
        ],
        "best_specialty": {"code": "B073", "title": "Сәулет"}
    }
}

# Minimal seed for rule-based questionnaire (без ML)
AI_QUESTION_SEED = [
    {
        "text": "В каком ты сейчас классе?",
        "answers": [
            {"text": "9 класс", "scores": {}},
            {"text": "10 класс", "scores": {}},
            {"text": "11 класс", "scores": {}},
            {"text": "Выпускник/колледж", "scores": {}}
        ],
    },
    {
        "text": "В каком году планируешь сдавать ЕНТ?",
        "answers": [
            {"text": "2026", "scores": {}},
            {"text": "2027", "scores": {}},
            {"text": "2028", "scores": {}},
            {"text": "2029 или позже", "scores": {}}
        ],
    },
    {
        "text": "Рассматриваешь ли поступление только в Казахстане или также за рубежом?",
        "answers": [
            {"text": "Только Казахстан", "scores": {}},
            {"text": "Казахстан и за рубежом", "scores": {}},
            {"text": "Скорее за рубежом", "scores": {}}
        ],
    },
    {
        "text": "Планируешь ли поступать на грант или допустимо платное обучение?",
        "answers": [
            {"text": "Только грант", "scores": {}},
            {"text": "Платное допустимо", "scores": {}},
            {"text": "Рассмотрю оба варианта", "scores": {}}
        ],
    },
    {
        "text": "Какие 3 предмета в школе даются тебе легче всего?",
        "answers": [
            {"text": "Математика, информатика, алгебра", "scores": {"math_inf": 3}},
            {"text": "Физика, математика, геометрия", "scores": {"math_phys": 3}},
            {"text": "Химия и биология", "scores": {"bio_chem": 3}},
            {"text": "Биология и география", "scores": {"bio_geo": 3}},
            {"text": "Химия и физика", "scores": {"chem_phys": 3}},
            {"text": "География и иностранный язык", "scores": {"geo_foreign": 3}},
            {"text": "Всемирная история и география", "scores": {"geo_hist": 3}},
            {"text": "История и основы права", "scores": {"hist_law": 3}},
            {"text": "Иностранный язык и история", "scores": {"foreign_hist": 3}},
            {"text": "Казахский язык и литература", "scores": {"kaz_lit": 3}},
            {"text": "Русский язык и литература", "scores": {"rus_lit": 3}},
            {"text": "Творческие дисциплины", "scores": {"creative": 3}}
        ],
    },
    {
        "text": "Какие 3 предмета даются сложнее всего?",
        "answers": [
            {"text": "Математика и информатика", "scores": {"geo_hist": 1}},
            {"text": "Физика и математика", "scores": {"geo_hist": 1}},
            {"text": "История и языки", "scores": {"math_inf": 1}},
            {"text": "Химия и биология", "scores": {}},
            {"text": "География и иностранный язык", "scores": {}},
            {"text": "Основы права", "scores": {}},
            {"text": "Языки и литература", "scores": {}},
            {"text": "Творческие дисциплины", "scores": {}},
            {"text": "Сложно выделить", "scores": {}}
        ],
    },
    {
        "text": "По каким предметам у тебя самые высокие оценки?",
        "answers": [
            {"text": "Математика/информатика", "scores": {"math_inf": 3}},
            {"text": "Физика/математика", "scores": {"math_phys": 3}},
            {"text": "Математика/география", "scores": {"math_geo": 3}},
            {"text": "Химия/биология", "scores": {"bio_chem": 3}},
            {"text": "Биология/география", "scores": {"bio_geo": 3}},
            {"text": "Химия/физика", "scores": {"chem_phys": 3}},
            {"text": "География/иностранный язык", "scores": {"geo_foreign": 3}},
            {"text": "Всемирная история/география", "scores": {"geo_hist": 3}},
            {"text": "Всемирная история/право", "scores": {"hist_law": 3}},
            {"text": "Иностранный язык/история", "scores": {"foreign_hist": 3}},
            {"text": "Казахский язык и литература", "scores": {"kaz_lit": 3}},
            {"text": "Русский язык и литература", "scores": {"rus_lit": 3}},
            {"text": "Творческие предметы", "scores": {"creative": 3}}
        ],
    },
    {
        "text": "По каким предметам ты готов(а) усиленно готовиться?",
        "answers": [
            {"text": "Математика и информатика", "scores": {"math_inf": 2}},
            {"text": "Физика и математика", "scores": {"math_phys": 2}},
            {"text": "Математика и география", "scores": {"math_geo": 2}},
            {"text": "Химия и биология", "scores": {"bio_chem": 2}},
            {"text": "Биология и география", "scores": {"bio_geo": 2}},
            {"text": "Химия и физика", "scores": {"chem_phys": 2}},
            {"text": "География и иностранный язык", "scores": {"geo_foreign": 2}},
            {"text": "История и география", "scores": {"geo_hist": 2}},
            {"text": "История и основы права", "scores": {"hist_law": 2}},
            {"text": "Иностранный язык и история", "scores": {"foreign_hist": 2}},
            {"text": "Казахский язык и литература", "scores": {"kaz_lit": 2}},
            {"text": "Русский язык и литература", "scores": {"rus_lit": 2}},
            {"text": "Творческие дисциплины", "scores": {"creative": 2}}
        ],
    },
    {
        "text": "Какая комбинация предметов ЕНТ тебе ближе?",
        "answers": [
            {"text": "Математика + Информатика", "scores": {"math_inf": 4}},
            {"text": "Математика + Физика", "scores": {"math_phys": 4}},
            {"text": "Математика + География", "scores": {"math_geo": 4}},
            {"text": "Биология + Химия", "scores": {"bio_chem": 4}},
            {"text": "Биология + География", "scores": {"bio_geo": 4}},
            {"text": "Химия + Физика", "scores": {"chem_phys": 4}},
            {"text": "География + Иностранный язык", "scores": {"geo_foreign": 4}},
            {"text": "Всемирная история + География", "scores": {"geo_hist": 4}},
            {"text": "Всемирная история + Основы права", "scores": {"hist_law": 4}},
            {"text": "Иностранный язык + Всемирная история", "scores": {"foreign_hist": 4}},
            {"text": "Казахский язык + Казахская литература", "scores": {"kaz_lit": 4}},
            {"text": "Русский язык + Русская литература", "scores": {"rus_lit": 4}},
            {"text": "Шығармашылық (творческий экзамен)", "scores": {"creative": 4}}
        ],
    },
    {
        "text": "Что тебе ближе в мышлении?",
        "answers": [
            {"text": "Логика и расчёты", "scores": {"math_inf": 2, "math_phys": 2}},
            {"text": "Тексты, языки, общение", "scores": {"geo_hist": 2}},
            {"text": "Творчество и визуал", "scores": {"creative": 2}},
            {"text": "Практика и действия", "scores": {"math_phys": 2, "chem_phys": 1}}
        ],
    },
    {
        "text": "Любишь ли ты решать задачи с формулами?",
        "answers": [
            {"text": "Да, это моё", "scores": {"math_phys": 3, "math_inf": 1, "chem_phys": 2}},
            {"text": "Иногда, если понятно", "scores": {"math_inf": 2, "math_geo": 1}},
            {"text": "Нет, избегаю", "scores": {"geo_hist": 2}}
        ],
    },
    {
        "text": "Насколько тебе комфортно анализировать большие объёмы информации?",
        "answers": [
            {"text": "Комфортно и интересно", "scores": {"math_inf": 2, "geo_hist": 1, "math_geo": 1}},
            {"text": "Могу, но устаю", "scores": {"math_phys": 1, "hist_law": 1}},
            {"text": "Сложно, предпочитаю меньше данных", "scores": {}}
        ],
    },
    {
        "text": "Какие профессии тебе кажутся интересными?",
        "answers": [
            {"text": "IT, анализ данных, разработка", "scores": {"math_inf": 3}},
            {"text": "Инженер, исследователь, техспециалист", "scores": {"math_phys": 3}},
            {"text": "Медицина, фармацевтика, биотехнологии", "scores": {"bio_chem": 3}},
            {"text": "Экология, природные ресурсы, агросфера", "scores": {"bio_geo": 3}},
            {"text": "Химтехнологии, материалы, промышленность", "scores": {"chem_phys": 3}},
            {"text": "Туризм, логистика, региональная экспертиза", "scores": {"geo_foreign": 3}},
            {"text": "Юриспруденция, госуправление, политика", "scores": {"hist_law": 3}},
            {"text": "Лингвистика, перевод, международные коммуникации", "scores": {"foreign_hist": 3}},
            {"text": "Филология, преподавание, работа с текстами", "scores": {"kaz_lit": 2, "rus_lit": 2}},
            {"text": "Дизайн, архитектура, искусство", "scores": {"creative": 3}},
            {"text": "Международные отношения, журналистика, гуманитарные сферы", "scores": {"geo_hist": 3}},
            {"text": "Пока не определился(ась)", "scores": {}}
        ],
    },
    {
        "text": "С чем тебе интереснее работать?",
        "answers": [
            {"text": "С людьми и коммуникацией", "scores": {"geo_hist": 2, "foreign_hist": 1}},
            {"text": "С данными и анализом", "scores": {"math_inf": 2}},
            {"text": "С техникой и устройствами", "scores": {"math_phys": 2, "chem_phys": 1}},
            {"text": "С документами и текстами", "scores": {"geo_hist": 1, "kaz_lit": 1, "rus_lit": 1}},
            {"text": "С природой и окружающей средой", "scores": {"bio_geo": 2}},
            {"text": "В креативной сфере", "scores": {"creative": 2}}
        ],
    },
    {
        "text": "Что для тебя важнее в работе?",
        "answers": [
            {"text": "Высокий доход", "scores": {"math_inf": 1}},
            {"text": "Стабильность", "scores": {"geo_hist": 1}},
            {"text": "Интересная работа", "scores": {}},
            {"text": "Свобода и гибкий график", "scores": {"math_inf": 1}}
        ],
    },
    {
        "text": "Где ты видишь себя после вуза?",
        "answers": [
            {"text": "Офис", "scores": {}},
            {"text": "Удалёнка", "scores": {"math_inf": 1}},
            {"text": "Гибридный формат", "scores": {}}
        ],
    },
    {
        "text": "Готов(а) ли ты к стрессу, дедлайнам и ответственности?",
        "answers": [
            {"text": "Да, нормально отношусь", "scores": {"math_inf": 1, "math_phys": 1}},
            {"text": "Скорее да", "scores": {"math_phys": 1}},
            {"text": "Скорее нет", "scores": {}}
        ],
    },
    {
        "text": "Предпочитаешь ли ты работать в команде или самостоятельно?",
        "answers": [
            {"text": "В команде", "scores": {"geo_hist": 1}},
            {"text": "Самостоятельно", "scores": {"math_inf": 1}},
            {"text": "Зависит от задачи", "scores": {}}
        ],
    },
    {
        "text": "Насколько ты готов(а) интенсивно готовиться к ЕНТ?",
        "answers": [
            {"text": "1 — очень слабо", "scores": {}},
            {"text": "2", "scores": {}},
            {"text": "3", "scores": {}},
            {"text": "4", "scores": {}},
            {"text": "5 — максимально", "scores": {}}
        ],
    },
    {
        "text": "Есть ли у тебя репетиторы или курсы?",
        "answers": [
            {"text": "Да, регулярно", "scores": {}},
            {"text": "Иногда/по отдельным предметам", "scores": {}},
            {"text": "Нет", "scores": {}}
        ],
    },
    {
        "text": "Готов(а) ли выбрать комбинацию с более высоким шансом на грант, даже если профессия не идеальна?",
        "answers": [
            {"text": "Да, это важно", "scores": {}},
            {"text": "Нет, хочу идеальную профессию", "scores": {}},
            {"text": "Зависит от вариантов", "scores": {}}
        ],
    },
    {
        "text": "Что для тебя важнее в будущем?",
        "answers": [
            {"text": "Деньги", "scores": {"math_inf": 1}},
            {"text": "Статус", "scores": {"math_phys": 1}},
            {"text": "Польза обществу", "scores": {"geo_hist": 1}},
            {"text": "Самореализация", "scores": {}}
        ],
    },
    {
        "text": "Хочешь ли, чтобы профессия была востребована через 10–15 лет?",
        "answers": [
            {"text": "Да, это принципиально", "scores": {"math_inf": 1}},
            {"text": "Не обязательно", "scores": {}},
            {"text": "Не уверен(а)", "scores": {}}
        ],
    },
    {
        "text": "Готов(а) ли ты к переобучению в будущем?",
        "answers": [
            {"text": "Да, готов(а)", "scores": {"math_inf": 1}},
            {"text": "Скорее да", "scores": {"math_inf": 1}},
            {"text": "Скорее нет", "scores": {}}
        ],
    },
    {
        "text": "Что вам интереснее всего в учебе?",
        "answers": [
            {"text": "Придумывать алгоритмы, писать код, оптимизировать процессы", "scores": {"math_inf": 3, "math_phys": 1}},
            {"text": "Понимать, как устроены явления и техника, считать формулы", "scores": {"math_phys": 3, "math_inf": 1}},
            {"text": "Разбираться в химических реакциях и организме человека", "scores": {"bio_chem": 3}},
            {"text": "Экология, природа и устойчивое развитие", "scores": {"bio_geo": 3}},
            {"text": "Изучать людей, историю, географию и взаимосвязи регионов", "scores": {"geo_hist": 3}},
            {"text": "Языки, культура и международные коммуникации", "scores": {"foreign_hist": 3}},
            {"text": "Творчество, визуал и дизайн", "scores": {"creative": 3}}
        ],
    },
    {
        "text": "Какую задачу выберете на проект?",
        "answers": [
            {"text": "Сделать веб-приложение или бота для реальной задачи", "scores": {"math_inf": 3, "math_phys": 1}},
            {"text": "Поставить эксперимент, измерить параметры, построить модель", "scores": {"math_phys": 3, "math_inf": 1}},
            {"text": "Собрать факты, карты и документы, чтобы объяснить событие", "scores": {"geo_hist": 3}},
            {"text": "Разработать экологический проект для региона", "scores": {"bio_geo": 3}},
            {"text": "Подготовить анализ рынка и логистики", "scores": {"math_geo": 3}},
            {"text": "Смоделировать химико-физический процесс в лаборатории", "scores": {"chem_phys": 3}},
            {"text": "Создать творческий проект: дизайн, медиа, сценография", "scores": {"creative": 3}}
        ],
    },
    {
        "text": "Что вас мотивирует в решении задач?",
        "answers": [
            {"text": "Чёткая логика, структурированные данные, автоматизация", "scores": {"math_inf": 3}},
            {"text": "Точные измерения, физические процессы, инженерные задачи", "scores": {"math_phys": 3, "math_inf": 1}},
            {"text": "Контекст людей, событий, стран; сравнение культур", "scores": {"geo_hist": 3, "math_phys": 1}},
            {"text": "Помогать людям через медицину и науку", "scores": {"bio_chem": 3}},
            {"text": "Развивать регионы и инфраструктуру", "scores": {"math_geo": 2, "geo_foreign": 1}},
            {"text": "Творческая свобода и визуальный результат", "scores": {"creative": 3}}
        ],
    },
    {
        "text": "Какие курсы вам больше всего заходят?",
        "answers": [
            {"text": "Информатика, программирование, математика", "scores": {"math_inf": 3, "math_phys": 1}},
            {"text": "Физика, инженерия, математика", "scores": {"math_phys": 3, "math_inf": 1}},
            {"text": "Химия, биология, анатомия", "scores": {"bio_chem": 3}},
            {"text": "Экология, география, устойчивое развитие", "scores": {"bio_geo": 3}},
            {"text": "История, география, обществознание", "scores": {"geo_hist": 3}},
            {"text": "Иностранные языки, культура, коммуникации", "scores": {"foreign_hist": 3}},
            {"text": "Литература, язык, филология", "scores": {"kaz_lit": 2, "rus_lit": 2}},
            {"text": "Дизайн, искусство, медиа", "scores": {"creative": 3}}
        ],
    },
]

db.init_app(app)
migrate.init_app(app, db)
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(TEST_IMAGE_FOLDER, exist_ok=True)
os.makedirs(HOMEWORK_UPLOAD_FOLDER, exist_ok=True)

# Auto-run migrations on startup (useful when Shell access is unavailable)
if os.environ.get('AUTO_MIGRATE') == '1':
    try:
        from flask_migrate import upgrade
        with app.app_context():
            upgrade()
            # Ensure a default admin exists on fresh databases
            if User.query.count() == 0:
                admin_username = os.environ.get('ADMIN_USERNAME', 'admin')
                admin_password = os.environ.get('ADMIN_PASSWORD', 'admin123')
                admin = User(
                    username=admin_username,
                    password=generate_password_hash(admin_password),
                    role='admin',
                    must_change_password=False,
                )
                db.session.add(admin)
                db.session.commit()
    except Exception as exc:
        print('AUTO_MIGRATE failed:', exc)
        raise


# Helpers
def current_user():
    username = session.get('user')
    if not username:
        return None
    return User.query.filter_by(username=username).first()


@app.context_processor
def inject_current_user():
    return {"current_user_obj": current_user()}

@app.context_processor
def inject_current_student():
    user = current_user()
    if not user or user.role != 'student':
        return {"current_student": None}
    return {"current_student": Student.query.filter_by(user_id=user.id).first()}


# Confirmation token helpers
def _signer():
    return URLSafeTimedSerializer(app.config.get('SECRET_KEY', app.secret_key), salt='confirm-actions')


def make_action_token(action: str, payload: dict) -> str:
    return _signer().dumps({'a': action, 'p': payload})


def load_action_token(token: str, max_age: int = 900):
    return _signer().loads(token, max_age=max_age)


@app.context_processor
def inject_utilities():
    return {"make_action_token": make_action_token}


@app.context_processor
def inject_language():
    return {"current_lang": _current_lang(), "languages": LANGUAGES}


def require_roles(*roles):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            user = current_user()
            if not user or (roles and user.role not in roles):
                flash('Доступ запрещён')
                return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


# Simple permission map and decorator
PERMISSIONS = {
    'publish_test': {'admin', 'teacher', 'mentor'},
    'moderate_materials': {'admin', 'content_moderator'},
    'create_course': {'admin', 'methodologist'},
}


def require_perms(*perms):
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if 'user' not in session:
                return redirect(url_for('login'))
            user = current_user()
            if not user:
                return redirect(url_for('login'))
            ok = any(user.role in PERMISSIONS.get(p, set()) for p in perms)
            if not ok:
                flash('Недостаточно прав для действия')
                return redirect(url_for('dashboard'))
            return fn(*args, **kwargs)
        return wrapper
    return decorator


def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def allowed_image(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def generate_temp_password() -> str:
    return os.urandom(6).hex()


def send_email(to_email: str, subject: str, body: str) -> bool:
    if not app.config.get('MAIL_USERNAME') or not app.config.get('MAIL_PASSWORD'):
        return False
    msg = Message(subject=subject, recipients=[to_email], body=body)
    try:
        mail.send(msg)
        return True
    except Exception as exc:
        app.logger.exception("Email send failed: %s", exc)
        return False


def build_external_url(endpoint: str, **values) -> str:
    base = app.config.get('APP_PUBLIC_URL')
    path = url_for(endpoint, **values)
    if base:
        return base.rstrip('/') + path
    return url_for(endpoint, _external=True, **values)


def find_student_user_by_identifier(identifier: str) -> User | None:
    ident = (identifier or '').strip()
    if not ident:
        return None
    if '@' in ident:
        student = Student.query.filter(func.lower(Student.email) == ident.lower()).first()
        return student.user if student else None
    return User.query.filter_by(username=ident).first()


def save_upload(file_storage, folder: str) -> str:
    """Save uploaded file with a unique name and return stored filename."""
    filename = secure_filename(file_storage.filename)
    save_path = os.path.join(folder, filename)
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(save_path):
        filename = f"{base}_{i}{ext}"
        save_path = os.path.join(folder, filename)
        i += 1
    file_storage.save(save_path)
    return filename


def allowed_homework_file(filename: str) -> bool:
    return allowed_file(filename) or allowed_image(filename)


def ensure_ai_seed():
    """Create or sync default AI questions/answers without wiping unrelated data."""
    existing = {q.text: q for q in AIQuestion.query.options(joinedload(AIQuestion.answers)).all()}
    for q in AI_QUESTION_SEED:
        q_obj = existing.get(q["text"])
        if not q_obj:
            q_obj = AIQuestion(text=q["text"])
            db.session.add(q_obj)
            db.session.flush()
        desired_answers = {a["text"]: a for a in q.get("answers", [])}
        existing_answers = {a.text: a for a in q_obj.answers}
        for text, ans_obj in existing_answers.items():
            if text not in desired_answers:
                db.session.delete(ans_obj)
        for text, ans in desired_answers.items():
            if text in existing_answers:
                existing_answers[text].scores = ans.get("scores", {})
            else:
                db.session.add(AIAnswer(question_id=q_obj.id, text=text, scores=ans.get("scores", {})))
    db.session.commit()


def calculate_ai_scores(answer_ids):
    """Deterministic rule-based scoring for ENT combinations."""
    base_scores = {k: 0 for k in ENT_COMBINATIONS.keys()}
    if not answer_ids:
        return base_scores, []
    answers = AIAnswer.query.filter(AIAnswer.id.in_(answer_ids)).all()
    for ans in answers:
        for comb, weight in (ans.scores or {}).items():
            if comb in base_scores:
                base_scores[comb] += weight
    sorted_pairs = sorted(base_scores.items(), key=lambda kv: kv[1], reverse=True)
    top3 = [{"key": k, "score": v} for k, v in sorted_pairs[:3]]
    return base_scores, top3


@app.after_request
def apply_language(response):
    if response.content_type and response.content_type.startswith("text/html"):
        if _current_lang() == "kz":
            data = response.get_data(as_text=True)
            response.set_data(_translate_html(data))
    return response


# CLI: init db
@app.cli.command('init-db')
def init_db():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        admin = User(username='admin', password=generate_password_hash('admin123'), role='admin')
        db.session.add(admin)
        db.session.commit()
    print('Database initialized with admin user.')


@app.cli.command('create-admin')
@click.option('--username', prompt=True)
@click.option('--password', prompt=True, hide_input=True, confirmation_prompt=True)
def create_admin(username, password):
    user = User.query.filter_by(username=username).first()
    if user:
        user.password = generate_password_hash(password)
        user.role = 'admin'
        message = 'Admin updated.'
    else:
        user = User(username=username, password=generate_password_hash(password), role='admin')
        db.session.add(user)
        message = 'Admin created.'
    db.session.commit()
    print(message)


# Auth
@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        identifier = request.form.get('username', '')
        u = find_student_user_by_identifier(identifier)
        if u and check_password_hash(u.password, request.form['password']):
            session['user'] = u.username
            if u.must_change_password:
                return redirect(url_for('force_password_change'))
            if u.role == 'student':
                return redirect(url_for('student_dashboard'))
            return redirect(url_for('dashboard'))
        flash('Неверные учетные данные')
    return render_template('login.html')


@app.route('/student-access', methods=['GET', 'POST'])
def student_access_request():
    if request.method == 'POST':
        identifier = request.form.get('identifier', '').strip()
        if not identifier:
            flash('Введите логин или email')
            return redirect(url_for('student_access_request'))
        user = find_student_user_by_identifier(identifier)
        student = Student.query.filter_by(user_id=user.id).first() if user else None
        if not user or user.role != 'student' or not student:
            flash('Если данные верные, мы отправим письмо с подтверждением')
            return redirect(url_for('login'))
        token = make_action_token('set_password', {'user_id': user.id})
        set_url = build_external_url('student_access_set_password', token=token)
        email_body = (
            "Вы запросили доступ к аккаунту студента.\n\n"
            f"Откройте ссылку, чтобы установить пароль:\n{set_url}\n\n"
            "Если вы не запрашивали доступ, просто проигнорируйте это письмо."
        )
        if send_email(student.email, 'Подтверждение доступа', email_body):
            flash('Письмо с подтверждением отправлено на почту.')
        else:
            flash('Не удалось отправить письмо. Проверьте настройки почты.')
            flash(f'Ссылка (dev): {set_url}')
        return redirect(url_for('login'))
    return render_template('student_access_request.html')


@app.route('/student-access/<token>', methods=['GET', 'POST'])
def student_access_set_password(token):
    try:
        data = load_action_token(token, max_age=3600)
    except SignatureExpired:
        flash('Ссылка устарела')
        return redirect(url_for('student_access_request'))
    except BadSignature:
        flash('Неверный токен')
        return redirect(url_for('student_access_request'))
    if data.get('a') != 'set_password':
        flash('Неверный токен')
        return redirect(url_for('student_access_request'))
    user_id = data.get('p', {}).get('user_id')
    user = User.query.get(user_id)
    student = Student.query.filter_by(user_id=user.id).first() if user else None
    if not user or user.role != 'student' or not student:
        flash('Пользователь не найден')
        return redirect(url_for('student_access_request'))
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm', '').strip()
        if not password or not confirm:
            flash('Заполните все поля')
            return redirect(url_for('student_access_set_password', token=token))
        if password != confirm:
            flash('Пароли не совпадают')
            return redirect(url_for('student_access_set_password', token=token))
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов')
            return redirect(url_for('student_access_set_password', token=token))
        user.password = generate_password_hash(password)
        user.must_change_password = False
        db.session.commit()
        flash('Пароль установлен. Войдите в систему.')
        return redirect(url_for('login'))
    return render_template('student_access_set_password.html', token=token)


@app.route('/force-password-change', methods=['GET', 'POST'])
def force_password_change():
    if 'user' not in session:
        return redirect(url_for('login'))
    u = current_user()
    if not u:
        return redirect(url_for('login'))
    if not u.must_change_password:
        if u.role == 'student':
            return redirect(url_for('student_dashboard'))
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm', '').strip()
        if not password or not confirm:
            flash('Заполните все поля')
            return redirect(url_for('force_password_change'))
        if password != confirm:
            flash('Пароли не совпадают')
            return redirect(url_for('force_password_change'))
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов')
            return redirect(url_for('force_password_change'))
        u.password = generate_password_hash(password)
        u.must_change_password = False
        db.session.commit()
        flash('Пароль обновлён')
        if u.role == 'student':
            return redirect(url_for('student_dashboard'))
        return redirect(url_for('dashboard'))
    return render_template('force_password_change.html')


def ensure_user_for_student(student: Student) -> User:
    if student.user:
        return student.user
    # create minimal user for student to reuse session machinery
    base_username = (student.email or f"student_{student.id}").strip()
    username = base_username
    if User.query.filter_by(username=username).first():
        username = f"{base_username}_{student.id}"
        if User.query.filter_by(username=username).first():
            username = f"student_{student.id}"
    # password не используется (вход по коду), но требуем смену после входа
    u = User(
        username=username,
        password=generate_password_hash(os.urandom(8).hex()),
        role='student',
        must_change_password=True
    )
    db.session.add(u)
    db.session.flush()
    student.user_id = u.id
    db.session.commit()
    return u


def ensure_login_user_for_student(student: Student) -> User:
    if student.user:
        return student.user
    base_username = (student.email or f"student_{student.id}").strip()
    username = base_username
    if User.query.filter_by(username=username).first():
        username = f"{base_username}_{student.id}"
        if User.query.filter_by(username=username).first():
            username = f"student_{student.id}"
    u = User(username=username, password=generate_password_hash(os.urandom(8).hex()), role='student')
    db.session.add(u)
    db.session.flush()
    student.user_id = u.id
    return u


@app.route('/student-reset', methods=['GET', 'POST'])
def student_reset_password():
    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        if not email:
            flash('Введите email')
            return redirect(url_for('student_reset_password'))
        student = Student.query.filter(func.lower(Student.email) == email.lower()).first()
        if not student:
            flash('Если email существует, мы отправим ссылку для сброса')
            return redirect(url_for('login'))
        user = ensure_login_user_for_student(student)
        db.session.commit()
        token = make_action_token('reset_password', {'user_id': user.id})
        reset_url = build_external_url('student_reset_password_token', token=token)
        email_body = (
            "Вы запросили сброс пароля.\n\n"
            f"Откройте ссылку, чтобы установить новый пароль:\n{reset_url}\n\n"
            "Если вы не запрашивали сброс, просто проигнорируйте это письмо."
        )
        if send_email(student.email, 'Сброс пароля', email_body):
            flash('Ссылка для сброса отправлена на почту.')
        else:
            flash('Не удалось отправить письмо. Проверьте настройки почты.')
            flash(f'Ссылка для сброса (dev): {reset_url}')
        return redirect(url_for('login'))
    return render_template('student_reset_password.html')


@app.route('/student-reset/<token>', methods=['GET', 'POST'])
def student_reset_password_token(token):
    try:
        data = load_action_token(token, max_age=3600)
    except SignatureExpired:
        flash('Ссылка для сброса устарела')
        return redirect(url_for('student_reset_password'))
    except BadSignature:
        flash('Неверный токен сброса')
        return redirect(url_for('student_reset_password'))
    if data.get('a') != 'reset_password':
        flash('Неверный токен сброса')
        return redirect(url_for('student_reset_password'))
    user_id = data.get('p', {}).get('user_id')
    user = User.query.get(user_id)
    if not user:
        flash('Пользователь не найден')
        return redirect(url_for('student_reset_password'))
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        confirm = request.form.get('confirm', '').strip()
        if not password or not confirm:
            flash('Заполните все поля')
            return redirect(url_for('student_reset_password_token', token=token))
        if password != confirm:
            flash('Пароли не совпадают')
            return redirect(url_for('student_reset_password_token', token=token))
        if len(password) < 6:
            flash('Пароль должен быть не менее 6 символов')
            return redirect(url_for('student_reset_password_token', token=token))
        user.password = generate_password_hash(password)
        user.must_change_password = False
        db.session.commit()
        flash('Пароль обновлён. Войдите в систему.')
        return redirect(url_for('login'))
    return render_template('student_reset_form.html', token=token)


@app.route('/student')
def student_dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    u = current_user()
    if not u or u.role != 'student':
        return redirect(url_for('dashboard'))
    # базовая статистика для студента
    st = Student.query.filter_by(user_id=u.id).first()
    courses = st.group.courses if st and st.group else []
    total_courses = len(courses)
    return render_template('student_dashboard.html', student=st, total_courses=total_courses, courses=courses)


@app.route('/student/profile')
def student_profile():
    if 'user' not in session:
        return redirect(url_for('login'))
    u = current_user()
    if not u or u.role != 'student':
        return redirect(url_for('dashboard'))
    st = Student.query.filter_by(user_id=u.id).first()
    if not st:
        flash('Профиль студента не найден')
        return redirect(url_for('student_dashboard'))
    return render_template('student_profile.html', student=st)


@app.route('/student/materials')
def student_materials():
    if 'user' not in session:
        return redirect(url_for('login'))
    u = current_user()
    if not u or u.role != 'student':
        return redirect(url_for('dashboard'))
    st = Student.query.filter_by(user_id=u.id).first()
    if not st or not st.group:
        flash('Студент не привязан к группе')
        return redirect(url_for('student_dashboard'))
    courses = list(st.group.courses)
    course_ids = [c.id for c in courses]
    selected_course_id = request.args.get('course_id', type=int)
    selected_course = None
    mats = []
    if selected_course_id and selected_course_id in course_ids:
        selected_course = next((c for c in courses if c.id == selected_course_id), None)
        mats = Material.query.filter(Material.course_id == selected_course_id).order_by(Material.created_at.desc()).all()
    return render_template('student_materials.html', materials=mats, courses=courses, selected_course=selected_course)


@app.route('/student/analytics')
def student_analytics():
    if 'user' not in session:
        return redirect(url_for('login'))
    u = current_user()
    if not u or u.role != 'student':
        return redirect(url_for('dashboard'))
    st = Student.query.filter_by(user_id=u.id).first()
    if not st:
        flash('Студент не найден')
        return redirect(url_for('student_dashboard'))
    # Aggregate accuracy by topic and difficulty
    stats = { 'topics': {}, 'difficulty': {} }
    for at in st.attempts:
        for ans in at.answers:
            q = ans.question
            if not q:
                continue
            topic = (q.topic or '—')
            diff = (q.difficulty or '—')
            is_correct = ans.option.is_correct if ans.option else False
            tstat = stats['topics'].setdefault(topic, {'total':0,'correct':0})
            tstat['total'] += 1; tstat['correct'] += 1 if is_correct else 0
            dstat = stats['difficulty'].setdefault(diff, {'total':0,'correct':0})
            dstat['total'] += 1; dstat['correct'] += 1 if is_correct else 0
    # Simple recommendations: pick latest materials from courses of student's group
    rec_materials = []
    if st.group:
        course_ids = [c.id for c in st.group.courses]
        rec_materials = Material.query.filter(Material.course_id.in_(course_ids)).order_by(Material.created_at.desc()).limit(10).all()
    return render_template('student_analytics.html', stats=stats, materials=rec_materials)


@app.route('/ai-test', methods=['GET', 'POST'])
def ai_test():
    if 'user' not in session:
        return redirect(url_for('login'))
    ensure_ai_seed()
    questions = AIQuestion.query.options(joinedload(AIQuestion.answers)).all()
    if request.method == 'POST':
        selected = []
        for q in questions:
            ans_id = request.form.get(f'question_{q.id}')
            if not ans_id:
                flash('Пожалуйста, отметьте ответы на все вопросы')
                return render_template('ai_test.html', questions=questions, combinations=ENT_COMBINATIONS)
            try:
                selected.append(int(ans_id))
            except ValueError:
                continue
        scores, top3 = calculate_ai_scores(selected)
        user = current_user()
        result = AIResult(user_id=user.id if user else None, scores=scores, top_combinations=top3)
        db.session.add(result)
        db.session.commit()
        session['last_ai_result_id'] = result.id
        return redirect(url_for('ai_result', result_id=result.id))
    return render_template('ai_test.html', questions=questions, combinations=ENT_COMBINATIONS)


@app.route('/ai-result')
def ai_result():
    if 'user' not in session:
        return redirect(url_for('login'))
    result_id = request.args.get('result_id', type=int) or session.get('last_ai_result_id')
    if not result_id:
        flash('Сначала пройдите опрос')
        return redirect(url_for('ai_test'))
    res = AIResult.query.get_or_404(result_id)
    enriched_top = []
    for item in res.top_combinations or []:
        key = item.get('key') if isinstance(item, dict) else None
        if not key or key not in ENT_COMBINATIONS:
            continue
        meta = ENT_COMBINATIONS[key]
        score = item.get('score', 0)
        if not score and res.scores:
            score = res.scores.get(key, 0)
        best_specialty = meta.get("best_specialty")
        if not best_specialty and meta.get("specialties"):
            best_specialty = meta["specialties"][0]
        enriched_top.append({
            "key": key,
            "title": meta["title"],
            "score": score,
            "description": meta["description"],
            "careers": meta["careers"],
            "faculties": meta.get("faculties", []),
            "specialties": meta.get("specialties", []),
            "best_specialty": best_specialty
        })
    sorted_scores = sorted((res.scores or {}).items(), key=lambda kv: kv[1], reverse=True)
    return render_template('ai_result.html', result=res, top=enriched_top, sorted_scores=sorted_scores, combinations=ENT_COMBINATIONS)


@app.route('/student/tests')
def student_tests():
    return redirect(url_for('available_tests'))


@app.route('/logout')
def logout():
    session.pop('user', None)
    return redirect(url_for('login'))


@app.route('/set-lang/<lang>')
def set_lang(lang):
    if lang in LANGUAGES:
        session['lang'] = lang
    next_url = request.args.get('next')
    return redirect(next_url or request.referrer or url_for('dashboard'))


@app.route('/dashboard')
def dashboard():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    if user and user.role == 'student':
        return redirect(url_for('student_dashboard'))
    if user and user.role == 'teacher':
        return render_template(
            'teacher_dashboard.html',
            total_students=Student.query.count(),
            total_courses=Course.query.count(),
            total_groups=Group.query.count(),
            total_tests=Test.query.count(),
            total_materials=Material.query.count(),
        )
    return render_template(
        'dashboard.html',
        total_students=Student.query.count(),
        total_courses=Course.query.count(),
        total_groups=Group.query.count(),
    )


# Materials
@app.route('/materials', methods=['GET'])
def materials():
    if 'user' not in session:
        return redirect(url_for('login'))
    course_id = request.args.get('course_id', type=int)
    if course_id:
        mats = Material.query.filter_by(course_id=course_id).order_by(Material.created_at.desc()).all()
        course = Course.query.get(course_id)
    else:
        mats = Material.query.order_by(Material.created_at.desc()).all()
        course = None
    courses = Course.query.all()
    return render_template('materials.html', materials=mats, courses=courses, selected_course=course, user=current_user())


@app.route('/materials/upload', methods=['POST'])
@require_roles('admin', 'teacher')
def upload_material():
    title = request.form.get('title', '').strip()
    description = request.form.get('description', '').strip()
    course_id = request.form.get('course_id', type=int)
    material_type = request.form.get('material_type', '').strip().lower()
    file = request.files.get('file')

    if not title or not course_id or not file:
        flash('Заполните все поля и выберите файл')
        return redirect(url_for('materials', course_id=course_id))
    if not allowed_file(file.filename):
        flash('Недопустимый тип файла')
        return redirect(url_for('materials', course_id=course_id))

    filename = secure_filename(file.filename)
    save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    base, ext = os.path.splitext(filename)
    i = 1
    while os.path.exists(save_path):
        filename = f"{base}_{i}{ext}"
        save_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        i += 1
    file.save(save_path)

    u = current_user()
    # auto-detect material type if not provided
    ext_lower = ext.lower().lstrip('.')
    if not material_type:
        if ext_lower in ('pdf',):
            material_type = 'pdf'
        elif ext_lower in ('mp4', 'mov', 'webm'):
            material_type = 'video'
        elif ext_lower in ('ppt', 'pptx'):
            material_type = 'presentation'
        elif ext_lower in ('doc', 'docx', 'txt'):
            material_type = 'doc'
        elif ext_lower in ('zip', 'rar', '7z'):
            material_type = 'archive'
        else:
            material_type = 'other'
    mat = Material(title=title, description=description, course_id=course_id, file_path=filename, uploaded_by=u.id if u else None, material_type=material_type)
    db.session.add(mat)
    db.session.commit()
    flash('Материал загружен')
    return redirect(url_for('materials', course_id=course_id))


@app.route('/materials/<int:material_id>/download')
def download_material(material_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    mat = Material.query.get_or_404(material_id)
    u = current_user()
    if u and u.role == 'student':
        student = Student.query.filter_by(user_id=u.id).first()
        if not student or not student.group:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
        course = Course.query.get(mat.course_id)
        if student.group not in course.groups:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
    return send_from_directory(app.config['UPLOAD_FOLDER'], mat.file_path, as_attachment=True)


@app.route('/test-images/<path:filename>')
def test_image(filename):
    if 'user' not in session:
        return redirect(url_for('login'))
    return send_from_directory(TEST_IMAGE_FOLDER, filename, as_attachment=False)


"""
@app.route('/materials/<int:material_id>/view')
def view_material(material_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    mat = Material.query.get_or_404(material_id)
    u = current_user()
    if u and u.role == 'student':
        student = Student.query.filter_by(user_id=u.id).first()
        if not student or not student.group:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
        course = Course.query.get(mat.course_id)
        if student.group not in course.groups:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
    return send_from_directory(app.config['UPLOAD_FOLDER'], mat.file_path, as_attachment=False)
"""

@app.route('/materials/<int:material_id>/view')
def view_material(material_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    mat = Material.query.get_or_404(material_id)
    u = current_user()
    if u and u.role == 'student':
        student = Student.query.filter_by(user_id=u.id).first()
        if not student or not student.group:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
        course = Course.query.get(mat.course_id)
        if student.group not in course.groups:
            flash('Нет доступа к материалу')
            return redirect(url_for('materials', course_id=mat.course_id))
    return send_from_directory(app.config['UPLOAD_FOLDER'], mat.file_path, as_attachment=False)


# Tests
@app.route('/tests', methods=['GET', 'POST'])
def tests():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    if user and user.role == 'student':
        return redirect(url_for('available_tests'))
    courses = Course.query.all()

    if request.method == 'POST':
        if not user or user.role not in ('admin', 'teacher'):
            flash('Недостаточно прав')
            return redirect(url_for('tests'))
        title = request.form.get('title', '').strip()
        course_id = request.form.get('course_id', type=int)
        is_published = bool(request.form.get('is_published'))
        duration_minutes = request.form.get('duration_minutes', type=int)
        one_way = bool(request.form.get('one_way'))
        if not title or not course_id:
            flash('Заполните все поля')
            return redirect(url_for('tests'))
        t = Test(
            title=title,
            course_id=course_id,
            is_published=is_published,
            duration_minutes=duration_minutes,
            one_way=one_way,
            is_homework=False,
        )
        db.session.add(t)
        db.session.commit()
        flash('Тест создан')
        return redirect(url_for('manage_test', test_id=t.id))

    all_tests = Test.query.filter_by(is_homework=False).order_by(Test.created_at.desc()).all()
    return render_template('tests.html', tests=all_tests, courses=courses, user=user)


@app.route('/tests/<int:test_id>', methods=['GET'])
@require_roles('admin', 'teacher')
def manage_test(test_id):
    t = Test.query.get_or_404(test_id)
    return render_template('test_manage.html', test=t)


@app.route('/tests/<int:test_id>/toggle-publish', methods=['POST'])
@require_roles('admin', 'teacher')
def toggle_publish_test(test_id):
    t = Test.query.get_or_404(test_id)
    t.is_published = not t.is_published
    db.session.commit()
    flash('Статус публикации изменён')
    return redirect(url_for('manage_test', test_id=test_id))


@app.route('/tests/<int:test_id>/add-question', methods=['POST'])
@require_roles('admin', 'teacher')
def add_question(test_id):
    t = Test.query.get_or_404(test_id)
    text = request.form.get('text', '').strip()
    topic = request.form.get('topic', '').strip()
    difficulty = request.form.get('difficulty', '').strip().lower() or None
    opt1 = request.form.get('opt1', '').strip()
    opt2 = request.form.get('opt2', '').strip()
    opt3 = request.form.get('opt3', '').strip()
    opt4 = request.form.get('opt4', '').strip()
    correct = request.form.get('correct')  # '1'..'4'
    q_image = request.files.get('question_image')
    opt_images = [
        request.files.get('opt1_image'),
        request.files.get('opt2_image'),
        request.files.get('opt3_image'),
        request.files.get('opt4_image'),
    ]

    if correct not in {'1', '2', '3', '4'}:
        flash('Выберите правильный вариант')
        return redirect(url_for('manage_test', test_id=t.id))

    if not text and not (q_image and q_image.filename):
        flash('Добавьте текст вопроса или изображение')
        return redirect(url_for('manage_test', test_id=t.id))

    options_text = [opt1, opt2, opt3, opt4]
    # Require at least 2 options with either text or image
    if not (options_text[0] or (opt_images[0] and opt_images[0].filename)) or not (options_text[1] or (opt_images[1] and opt_images[1].filename)):
        flash('Заполните минимум 2 варианта (текст или изображение)')
        return redirect(url_for('manage_test', test_id=t.id))

    correct_idx = int(correct) - 1
    if correct_idx < 0 or correct_idx > 3:
        flash('Выберите правильный вариант')
        return redirect(url_for('manage_test', test_id=t.id))
    if not (options_text[correct_idx] or (opt_images[correct_idx] and opt_images[correct_idx].filename)):
        flash('Правильный вариант не заполнен')
        return redirect(url_for('manage_test', test_id=t.id))

    if q_image and q_image.filename and not allowed_image(q_image.filename):
        flash('Недопустимый тип файла изображения')
        return redirect(url_for('manage_test', test_id=t.id))
    for f in opt_images:
        if f and f.filename and not allowed_image(f.filename):
            flash('Недопустимый тип файла изображения')
            return redirect(url_for('manage_test', test_id=t.id))

    q_image_name = save_upload(q_image, TEST_IMAGE_FOLDER) if q_image and q_image.filename else None
    q = Question(
        test_id=t.id,
        text=text or '',
        image_path=q_image_name,
        topic=topic or None,
        difficulty=difficulty if difficulty in {'easy', 'medium', 'hard'} else None
    )
    db.session.add(q)
    db.session.flush()
    for idx, (txt, img) in enumerate(zip(options_text, opt_images), start=1):
        if not txt and not (img and img.filename):
            continue
        img_name = save_upload(img, TEST_IMAGE_FOLDER) if img and img.filename else None
        db.session.add(
            Option(
                question_id=q.id,
                text=txt or '',
                image_path=img_name,
                is_correct=(str(idx) == correct)
            )
        )
    db.session.commit()
    flash('Вопрос добавлен')
    return redirect(url_for('manage_test', test_id=t.id))


@app.route('/tests/available')
def available_tests():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    if not user or user.role != 'student':
        flash('Доступно только студентам')
        return redirect(url_for('tests'))
    student = Student.query.filter_by(user_id=user.id).first()
    if not student or not student.group:
        flash('Студент не привязан к группе')
        return render_template('tests_available.html', tests=[], courses=[], selected_course=None)
    courses = list(student.group.courses)
    course_ids = [c.id for c in courses]
    selected_course_id = request.args.get('course_id', type=int)
    selected_course = None
    q = Test.query.filter(Test.course_id.in_(course_ids), Test.is_published == True, Test.is_homework == False)
    if selected_course_id and selected_course_id in course_ids:
        selected_course = next((c for c in courses if c.id == selected_course_id), None)
        q = q.filter(Test.course_id == selected_course_id)
    tlist = q.order_by(Test.created_at.desc()).all()
    return render_template('tests_available.html', tests=tlist, courses=courses, selected_course=selected_course)


@app.route('/homework', methods=['GET', 'POST'])
def homework():
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()

    # Student view: list homework for their courses
    if user and user.role == 'student':
        student = Student.query.filter_by(user_id=user.id).first()
        if not student or not student.group:
            flash('Студент не привязан к группе')
            return render_template('homework.html', homeworks=[], courses=[], selected_course=None)
        courses = list(student.group.courses)
        course_ids = [c.id for c in courses]
        selected_course_id = request.args.get('course_id', type=int)
        selected_course = None
        q = Test.query.filter(Test.course_id.in_(course_ids), Test.is_published == True, Test.is_homework == True)
        if selected_course_id and selected_course_id in course_ids:
            selected_course = next((c for c in courses if c.id == selected_course_id), None)
            q = q.filter(Test.course_id == selected_course_id)
        hlist = q.order_by(Test.created_at.desc()).all()
        from datetime import datetime as _dt
        now = _dt.utcnow()
        for h in hlist:
            h.remaining_seconds = None
            if h.due_at:
                h.remaining_seconds = max(0, int((h.due_at - now).total_seconds()))
        return render_template('homework.html', homeworks=hlist, courses=courses, selected_course=selected_course)

    # Teacher/admin view: create + list homework
    courses = Course.query.all()
    if request.method == 'POST':
        if not user or user.role not in ('admin', 'teacher'):
            flash('Недостаточно прав')
            return redirect(url_for('homework'))
        title = request.form.get('title', '').strip()
        course_id = request.form.get('course_id', type=int)
        is_published = bool(request.form.get('is_published'))
        homework_text = request.form.get('homework_text', '').strip()
        homework_file = request.files.get('homework_file')
        due_at_str = request.form.get('due_at', '').strip()
        due_at = None
        if due_at_str:
            from datetime import datetime as _dt
            try:
                due_at = _dt.fromisoformat(due_at_str)
            except ValueError:
                flash('Неверный формат дедлайна')
                return redirect(url_for('homework'))
        if not title or not course_id:
            flash('Заполните все поля')
            return redirect(url_for('homework'))
        file_name = None
        if homework_file and homework_file.filename:
            if not allowed_homework_file(homework_file.filename):
                flash('Недопустимый тип файла')
                return redirect(url_for('homework'))
            file_name = save_upload(homework_file, HOMEWORK_UPLOAD_FOLDER)
        t = Test(
            title=title,
            course_id=course_id,
            is_published=is_published,
            is_homework=True,
            homework_text=homework_text or None,
            homework_file_path=file_name,
            due_at=due_at,
        )
        db.session.add(t)
        db.session.commit()
        flash('Домашнее задание создано')
        return redirect(url_for('homework'))

    homeworks = Test.query.filter_by(is_homework=True).order_by(Test.created_at.desc()).all()
    return render_template('homework.html', homeworks=homeworks, courses=courses, selected_course=None)


@app.route('/tests/<int:test_id>/homework', methods=['GET', 'POST'])
def homework_submit(test_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    t = Test.query.get_or_404(test_id)
    if not t.is_homework:
        return redirect(url_for('start_test', test_id=t.id))
    if not user or user.role != 'student':
        flash('Доступно только студентам')
        return redirect(url_for('tests'))
    student = Student.query.filter_by(user_id=user.id).first()
    if not student or not student.group or t.course not in student.group.courses:
        flash('Нет доступа к тесту')
        return redirect(url_for('available_tests'))

    from datetime import datetime as _dt
    now = _dt.utcnow()
    is_late = bool(t.due_at and now > t.due_at)
    remaining_seconds = None
    if t.due_at:
        remaining_seconds = max(0, int((t.due_at - now).total_seconds()))

    submission = HomeworkSubmission.query.filter_by(test_id=t.id, student_id=student.id).order_by(HomeworkSubmission.submitted_at.desc()).first()
    if request.method == 'POST':
        if is_late:
            flash('Дедлайн прошёл')
            return redirect(url_for('homework_submit', test_id=t.id))
        text = request.form.get('text', '').strip()
        file = request.files.get('file')
        if not text and not (file and file.filename):
            flash('Добавьте текст или файл')
            return redirect(url_for('homework_submit', test_id=t.id))
        file_name = None
        if file and file.filename:
            if not allowed_homework_file(file.filename):
                flash('Недопустимый тип файла')
                return redirect(url_for('homework_submit', test_id=t.id))
            file_name = save_upload(file, HOMEWORK_UPLOAD_FOLDER)
        new_sub = HomeworkSubmission(test_id=t.id, student_id=student.id, text=text or None, file_path=file_name, submitted_at=_dt.utcnow())
        db.session.add(new_sub)
        db.session.commit()
        flash('Домашнее задание отправлено')
        return redirect(url_for('homework_submit', test_id=t.id))

    return render_template('homework_submit.html', test=t, submission=submission, is_late=is_late, remaining_seconds=remaining_seconds)


@app.post('/homework/submission/<int:submission_id>/grade')
@require_roles('admin', 'teacher')
def grade_homework(submission_id):
    sub = HomeworkSubmission.query.get_or_404(submission_id)
    score = request.form.get('score', '').strip()
    if score == '':
        sub.score = None
    else:
        try:
            sub.score = int(score)
        except ValueError:
            flash('Неверный балл')
            return redirect(url_for('test_results', test_id=sub.test_id))
    db.session.commit()
    flash('Оценка сохранена')
    return redirect(url_for('test_results', test_id=sub.test_id))


@app.route('/homework/<int:submission_id>/download')
def homework_download(submission_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    sub = HomeworkSubmission.query.get_or_404(submission_id)
    if not sub.file_path:
        flash('Файл не найден')
        return redirect(url_for('test_results', test_id=sub.test_id))
    user = current_user()
    if user and user.role == 'student':
        student = Student.query.filter_by(user_id=user.id).first()
        if not student or sub.student_id != student.id:
            flash('Нет доступа')
            return redirect(url_for('available_tests'))
    return send_from_directory(HOMEWORK_UPLOAD_FOLDER, sub.file_path, as_attachment=True)


@app.route('/homework/<int:test_id>/attachment')
def homework_attachment(test_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    t = Test.query.get_or_404(test_id)
    if not t.is_homework or not t.homework_file_path:
        flash('Файл не найден')
        return redirect(url_for('homework'))
    user = current_user()
    if user and user.role == 'student':
        student = Student.query.filter_by(user_id=user.id).first()
        if not student or not student.group or t.course not in student.group.courses:
            flash('Нет доступа')
            return redirect(url_for('homework'))
    return send_from_directory(HOMEWORK_UPLOAD_FOLDER, t.homework_file_path, as_attachment=True)


@app.route('/tests/<int:test_id>/start', methods=['GET'])
def start_test(test_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    t = Test.query.get_or_404(test_id)
    if t.is_homework:
        return redirect(url_for('homework_submit', test_id=t.id))
    if user and user.role == 'student':
        student = Student.query.filter_by(user_id=user.id).first()
        if not student or not student.group or t.course not in student.group.courses:
            flash('Нет доступа к тесту')
            return redirect(url_for('available_tests'))
        # ensure attempt exists and compute remaining seconds
        key = f"attempt_test_{t.id}"
        attempt_id = session.get(key)
        attempt = None
        if attempt_id:
            attempt = Attempt.query.get(attempt_id)
        if not attempt:
            attempt = Attempt(test_id=t.id, student_id=student.id)
            db.session.add(attempt)
            db.session.commit()
            session[key] = attempt.id
        remaining_seconds = None
        if t.duration_minutes:
            from datetime import datetime as _dt, timedelta as _td
            end_time = attempt.started_at + _td(minutes=t.duration_minutes)
            remaining_seconds = max(0, int((end_time - _dt.utcnow()).total_seconds()))
        return render_template('test_take.html', test=t, attempt=attempt, remaining_seconds=remaining_seconds)
    # Non-students (e.g., teachers previewing) still render safely
    return render_template('test_take.html', test=t, attempt=None, remaining_seconds=None)


@app.route('/tests/<int:test_id>/submit', methods=['POST'])
def submit_test(test_id):
    if 'user' not in session:
        return redirect(url_for('login'))
    user = current_user()
    t = Test.query.get_or_404(test_id)
    if t.is_homework:
        return redirect(url_for('homework_submit', test_id=t.id))

    student_id = None
    if user and user.role == 'student':
        student = Student.query.filter_by(user_id=user.id).first()
        if not student:
            flash('Нет профиля студента')
            return redirect(url_for('available_tests'))
        student_id = student.id

    total = len(t.questions)
    score = 0
    attempt = None
    if student_id:
        key = f"attempt_test_{t.id}"
        aid = session.get(key)
        if aid:
            attempt = Attempt.query.get(aid)
        if not attempt:
            attempt = Attempt(test_id=t.id, student_id=student_id)
            db.session.add(attempt)
            db.session.flush()

    for q in t.questions:
        sel = request.form.get(f'question_{q.id}')
        if not sel:
            continue
        opt = Option.query.get(int(sel))
        if attempt:
            db.session.add(AttemptAnswer(attempt_id=attempt.id, question_id=q.id, option_id=opt.id))
        if opt.is_correct:
            score += 1

    if attempt:
        attempt.score = score
        from datetime import datetime as _dt
        attempt.finished_at = _dt.utcnow()
        db.session.commit()
    # For non-students (preview), no DB writes; show computed score only
    return render_template('test_result.html', test=t, attempt=attempt, total=total, score=score)


# Confirmation page for sensitive actions
@app.get('/confirm/<token>')
def confirm_get(token):
    try:
        data = load_action_token(token)
    except SignatureExpired:
        flash('Ссылка подтверждения устарела')
        return redirect(url_for('dashboard'))
    except BadSignature:
        flash('Неверный токен подтверждения')
        return redirect(url_for('dashboard'))
    return render_template('confirm.html', data=data, token=token)


@app.post('/confirm/<token>')
def confirm_post(token):
    try:
        data = load_action_token(token)
    except Exception:
        flash('Неверное подтверждение')
        return redirect(url_for('dashboard'))
    action, payload = data.get('a'), data.get('p') or {}
    if action == 'toggle_publish_test':
        tid = int(payload.get('test_id'))
        t = Test.query.get_or_404(tid)
        t.is_published = not t.is_published
        db.session.commit()
        flash('Статус публикации обновлён')
        return redirect(url_for('manage_test', test_id=tid))
    flash('Неизвестное действие')
    return redirect(url_for('dashboard'))


@app.route('/tests/<int:test_id>/results')
@require_roles('admin', 'teacher')
def test_results(test_id):
    t = Test.query.get_or_404(test_id)
    attempts = Attempt.query.filter_by(test_id=test_id).order_by(Attempt.started_at.desc()).all()
    submissions = HomeworkSubmission.query.filter_by(test_id=test_id).order_by(HomeworkSubmission.submitted_at.desc()).all()
    return render_template('test_results.html', test=t, attempts=attempts, submissions=submissions)


# Users admin (create users and link to students)
@app.route('/users', methods=['GET', 'POST'])
@require_roles('admin')
def users_admin():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '').strip()
        role = request.form.get('role', 'student')
        student_id = request.form.get('student_id', type=int)
        student_name = request.form.get('student_name', '').strip()
        student_email = request.form.get('student_email', '').strip()
        lecture_id = request.form.get('lecture_id', type=int)
        if not username or not password or role not in ('admin', 'teacher', 'student'):
            flash('Заполните все поля')
            return redirect(url_for('users_admin'))
        if User.query.filter_by(username=username).first():
            flash('Такой пользователь уже существует')
            return redirect(url_for('users_admin'))
        if role == 'teacher' and lecture_id:
            lecture = Lecture.query.get(lecture_id)
            if lecture and lecture.user_id:
                flash('Этот учитель уже привязан к аккаунту')
                return redirect(url_for('users_admin'))
        if role == 'student' and not student_id:
            if not student_name or not student_email:
                flash('Для роли student укажите имя и email или выберите существующего студента')
                return redirect(url_for('users_admin'))
            existing_student = Student.query.filter_by(email=student_email).first()
            if existing_student and existing_student.user_id:
                flash('Этот email уже привязан к аккаунту студента')
                return redirect(url_for('users_admin'))
        u = User(username=username, password=generate_password_hash(password), role=role)
        db.session.add(u)
        db.session.flush()
        if role == 'student':
            if student_id:
                st = Student.query.get(student_id)
                if st:
                    st.user_id = u.id
            else:
                if existing_student:
                    existing_student.name = student_name or existing_student.name
                    existing_student.user_id = u.id
                else:
                    st = Student(name=student_name, email=student_email, user_id=u.id)
                    db.session.add(st)
        if role == 'teacher' and lecture_id:
            lecture = Lecture.query.get(lecture_id)
            if lecture:
                lecture.user_id = u.id
        db.session.commit()
        flash('Пользователь создан')
        return redirect(url_for('users_admin'))

    lectures = Lecture.query.all()
    lecture_map = {l.user_id: l for l in lectures if l.user_id}
    return render_template(
        'users.html',
        users=User.query.all(),
        students=Student.query.all(),
        lectures=lectures,
        lecture_map=lecture_map,
    )


# Existing routes from the original app (entities management)

@app.route('/lectures', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def lectures():
    if request.method == 'POST':
        name = request.form['name']
        surname = request.form['surname']
        title = request.form.get('title', '')
        description = request.form.get('description', '')
        existing = Lecture.query.filter_by(name=name, surname=surname).first()
        if existing:
            flash('Лектор с таким именем уже существует')
        else:
            lecture = Lecture(name=name, surname=surname, title=title, description=description)
            db.session.add(lecture)
            db.session.commit()
            flash('Лектор успешно добавлен')
    return render_template('lectures.html', lectures=Lecture.query.all())


@app.route('/lectures/edit/<int:id>', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def edit_lecture(id):
    lecture = Lecture.query.get_or_404(id)
    if request.method == 'POST':
        lecture.name = request.form['name']
        lecture.surname = request.form['surname']
        lecture.title = request.form.get('title', '')
        lecture.description = request.form.get('description', '')
        db.session.commit()
        flash('Лектор обновлён')
        return redirect(url_for('lectures'))
    return render_template('edit_lecture.html', lecture=lecture)


@app.route('/lectures/delete/<int:id>')
@require_roles('admin', 'teacher')
def delete_lecture(id):
    lecture = Lecture.query.get_or_404(id)
    db.session.delete(lecture)
    db.session.commit()
    flash('Лектор удалён')
    return redirect(url_for('lectures'))


@app.route('/employees')
@require_roles('admin')
def employees():
    return render_template('employees.html', employees=Employee.query.all())


@app.route('/employee/add', methods=['GET', 'POST'])
@require_roles('admin')
def add_employee():
    departments = Department.query.all()
    if request.method == 'POST':
        name = request.form['name']
        position = request.form['position']
        department_id = request.form['department_id']
        new_employee = Employee(name=name, position=position, department_id=department_id)
        db.session.add(new_employee)
        db.session.commit()
        flash('Сотрудник добавлен!')
        return redirect(url_for('employees'))
    return render_template('employee_form.html', departments=departments)


@app.route('/employee/edit/<int:employee_id>', methods=['GET', 'POST'])
@require_roles('admin')
def edit_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    departments = Department.query.all()
    if request.method == 'POST':
        employee.name = request.form['name']
        employee.position = request.form['position']
        employee.department_id = request.form['department_id']
        db.session.commit()
        flash('Сотрудник обновлён!')
        return redirect(url_for('employees'))
    return render_template('employee_form.html', employee=employee, departments=departments)


@app.route('/employee/delete/<int:employee_id>', methods=['POST'])
@require_roles('admin')
def delete_employee(employee_id):
    employee = Employee.query.get_or_404(employee_id)
    db.session.delete(employee)
    db.session.commit()
    flash('Сотрудник удалён.')
    return redirect(url_for('employees'))


@app.route('/departments', methods=['GET', 'POST'])
@require_roles('admin')
def departments():
    if request.method == 'POST':
        name = request.form['name']
        department = Department(name=name)
        db.session.add(department)
        db.session.commit()
        flash('Отдел добавлен!')
    return render_template('departments.html', departments=Department.query.all())


@app.route('/departments/delete/<int:department_id>', methods=['POST'])
@require_roles('admin')
def delete_department(department_id):
    department = Department.query.get_or_404(department_id)
    db.session.delete(department)
    db.session.commit()
    flash('Отдел удалён.')
    return redirect(url_for('departments'))


@app.route('/groups', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def groups():
    if request.method == 'POST':
        name = request.form['name']
        description = request.form['description']
        existing = Group.query.filter_by(name=name).first()
        if existing:
            flash('Группа с таким именем уже существует')
        else:
            group = Group(name=name, description=description)
            db.session.add(group)
            db.session.commit()
            flash('Группа успешно создана')
    return render_template('groups.html', groups=Group.query.all())


@app.route('/groups/delete/<int:id>')
@require_roles('admin', 'teacher')
def delete_group(id):
    group = Group.query.get_or_404(id)
    # отвяжем студентов, чтобы каскадно не падало
    for s in group.students:
        s.group_id = None
    db.session.delete(group)
    db.session.commit()
    flash('Группа удалена')
    return redirect(url_for('groups'))


@app.route('/groups/edit/<int:id>', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def edit_group(id):
    group = Group.query.get_or_404(id)
    if request.method == 'POST':
        group.name = request.form['name']
        group.description = request.form['description']
        db.session.commit()
        flash('Данные группы обновлены')
        return redirect(url_for('groups'))
    return render_template('edit_group.html', group=group)


@app.route('/students', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def students():
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        username = request.form.get('username', '').strip()
        group_id = request.form.get('group_id')
        if Student.query.filter_by(email=email).first():
            flash('Студент с таким email уже существует')
        else:
            base_username = username or (email.split('@')[0] if '@' in email else name)
            base_username = (base_username or '').strip() or f"student_{os.urandom(3).hex()}"
            final_username = base_username
            i = 1
            while User.query.filter_by(username=final_username).first():
                final_username = f"{base_username}_{i}"
                i += 1
            student = Student(name=name, email=email)
            if group_id:
                student.group_id = int(group_id)
            db.session.add(student)
            db.session.flush()
            user = User(
                username=final_username,
                password=generate_password_hash(generate_temp_password()),
                role='student',
                must_change_password=True
            )
            db.session.add(user)
            db.session.flush()
            student.user_id = user.id
            db.session.commit()
            token = make_action_token('set_password', {'user_id': user.id})
            set_url = build_external_url('student_access_set_password', token=token)
            email_body = (
                "Добро пожаловать!\n\n"
                f"Ваш логин: {final_username}\n"
                f"Установите пароль по ссылке:\n{set_url}\n\n"
                "Если это письмо попало к вам по ошибке, просто проигнорируйте его."
            )
            if send_email(student.email, 'Установка пароля', email_body):
                flash(f'Студент успешно добавлен. Логин: {final_username}. Письмо отправлено.')
            else:
                flash(f'Студент успешно добавлен. Логин: {final_username}.')
                flash('Не удалось отправить письмо. Проверьте настройки почты.')
                flash(f'Ссылка (dev): {set_url}')
    return render_template('students.html', students=Student.query.all(), groups=Group.query.all())


@app.route('/students/delete/<int:id>')
@require_roles('admin', 'teacher')
def delete_student(id):
    st = Student.query.get_or_404(id)
    db.session.delete(st)
    db.session.commit()
    flash('Студент удалён')
    return redirect(url_for('students'))


@app.route('/students/edit/<int:id>', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def edit_student(id):
    st = Student.query.get_or_404(id)
    if request.method == 'POST':
        st.name = request.form['name']
        st.email = request.form['email']
        username = request.form.get('username', '').strip()
        group_id = request.form.get('group_id')
        st.group_id = int(group_id) if group_id else None
        if username:
            if st.user:
                if st.user.username != username and User.query.filter_by(username=username).first():
                    flash('Такой логин уже существует')
                    return redirect(url_for('edit_student', id=st.id))
                st.user.username = username
            else:
                temp_password = generate_temp_password()
                user = User(
                    username=username,
                    password=generate_password_hash(temp_password),
                    role='student',
                    must_change_password=True
                )
                db.session.add(user)
                db.session.flush()
                st.user_id = user.id
                flash(f'Аккаунт создан. Логин: {username} · Временный пароль: {temp_password}')
        db.session.commit()
        flash('Данные студента обновлены')
        return redirect(url_for('students'))
    return render_template('edit_student.html', student=st, groups=Group.query.all())


@app.route('/students/<int:id>/reset-temp-password', methods=['POST'])
@require_roles('admin', 'teacher')
def reset_student_temp_password(id):
    st = Student.query.get_or_404(id)
    user = ensure_login_user_for_student(st)
    token = make_action_token('set_password', {'user_id': user.id})
    set_url = build_external_url('student_access_set_password', token=token)
    email_body = (
        "Для установки пароля используйте ссылку ниже:\n\n"
        f"{set_url}\n\n"
        "Если вы не запрашивали доступ, просто проигнорируйте это письмо."
    )
    if send_email(st.email, 'Установка пароля', email_body):
        flash('Ссылка для установки пароля отправлена на почту.')
    else:
        flash('Не удалось отправить письмо. Проверьте настройки почты.')
        flash(f'Ссылка (dev): {set_url}')
    return redirect(url_for('edit_student', id=st.id))


@app.route('/courses', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def courses():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        db.session.add(Course(title=title, description=description))
        db.session.commit()
        flash('Курс успешно создан')
    return render_template('courses.html', courses=Course.query.all())


@app.route('/courses/delete/<int:id>')
@require_roles('admin', 'teacher')
def delete_course(id):
    c = Course.query.get_or_404(id)
    # Clean up dependent records to avoid FK/NOT NULL violations
    if c.groups:
        c.groups.clear()
    for material in list(c.materials):
        db.session.delete(material)
    for test in list(c.tests):
        db.session.delete(test)
    db.session.delete(c)
    db.session.commit()
    flash('Курс удалён')
    return redirect(url_for('courses'))


@app.route('/courses/edit/<int:id>', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def edit_course(id):
    c = Course.query.get_or_404(id)
    if request.method == 'POST':
        c.title = request.form.get('title', c.title)
        c.description = request.form.get('description', c.description)
        db.session.commit()
        flash('Данные курса обновлены')
        return redirect(url_for('courses'))
    return render_template('edit_course.html', course=c)


@app.route('/course_registration')
@require_roles('admin', 'teacher')
def course_registration():
    return render_template('course_registration.html', courses=Course.query.all())


@app.route('/course/<int:course_id>/register', methods=['GET', 'POST'])
@require_roles('admin', 'teacher')
def register_groups_to_course(course_id):
    course = Course.query.get_or_404(course_id)
    if request.method == 'POST':
        group_ids = request.form.getlist('group_ids')
        for gid in group_ids:
            g = Group.query.get(int(gid))
            if g and g not in course.groups:
                course.groups.append(g)
        db.session.commit()
        flash(f"Группы успешно зарегистрированы на курс '{course.title}'")
        return redirect(url_for('course_registration'))
    all_groups = Group.query.all()
    return render_template('register_groups.html', course=course, all_groups=all_groups, registered_groups=course.groups)


@app.errorhandler(404)
def not_found_page(error):
    return render_template('404.html'), 404


@app.route('/course/<int:course_id>/unregister/<int:group_id>')
@require_roles('admin', 'teacher')
def unregister_group_from_course(course_id, group_id):
    course = Course.query.get_or_404(course_id)
    group = Group.query.get_or_404(group_id)
    if group in course.groups:
        course.groups.remove(group)
        db.session.commit()
        flash(f"Группа '{group.name}' отписана от курса '{course.title}'")
    return redirect(url_for('register_groups_to_course', course_id=course_id))


if __name__ == '__main__':
    # Disable reloader to avoid double-start and permission errors in some environments
    app.run(debug=True, use_reloader=False)
