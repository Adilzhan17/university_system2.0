# -*- coding: utf-8 -*-
from extensions import db
from datetime import datetime


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='admin')
    must_change_password = db.Column(db.Boolean, nullable=False, default=False)


class Lecture(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    surname = db.Column(db.String(100), nullable=False, unique=True)
    title = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    user = db.relationship('User', foreign_keys=[user_id])


class Department(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)

    employees = db.relationship('Employee', backref='department', lazy=True)


class Employee(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    position = db.Column(db.String(100))
    department_id = db.Column(db.Integer, db.ForeignKey('department.id'))


class Group(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

    students = db.relationship('Student', backref='group', lazy=True)

    def __repr__(self):
        return f'<Group {self.name}>'


class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(150), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    user = db.relationship('User', foreign_keys=[user_id])

    group_id = db.Column(db.Integer, db.ForeignKey('group.id'), nullable=True)
    # код для входа без пароля (портал студента)
    access_code = db.Column(db.String(64), unique=True)

    def __repr__(self):
        return f'<Student {self.name}>'


class Course(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)

    def __repr__(self):
        return f'<Course {self.title}>'


group_course_association = db.Table(
    'group_course',
    db.Column('group_id', db.Integer, db.ForeignKey('group.id'), primary_key=True),
    db.Column('course_id', db.Integer, db.ForeignKey('course.id'), primary_key=True),
)


Group.courses = db.relationship(
    'Course', secondary=group_course_association, backref=db.backref('groups', lazy=True)
)


class Material(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    file_path = db.Column(db.String(300), nullable=False)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('Course', backref=db.backref('materials', lazy=True))
    uploader = db.relationship('User', foreign_keys=[uploaded_by])
    # content type and external hosting
    material_type = db.Column(db.String(20), nullable=False, default='other')
    external_url = db.Column(db.String(500))


# Quiz/Test models
class Test(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    course_id = db.Column(db.Integer, db.ForeignKey('course.id'), nullable=False)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    course = db.relationship('Course', backref=db.backref('tests', lazy=True))
    # ENT settings
    duration_minutes = db.Column(db.Integer)
    one_way = db.Column(db.Boolean, default=False, nullable=False)
    due_at = db.Column(db.DateTime)
    is_homework = db.Column(db.Boolean, default=False, nullable=False)
    homework_text = db.Column(db.Text)
    homework_file_path = db.Column(db.String(300))


class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    text = db.Column(db.Text, nullable=False)
    image_path = db.Column(db.String(255))

    test = db.relationship('Test', backref=db.backref('questions', lazy=True, cascade='all, delete-orphan'))
    # analytics/adaptive fields
    topic = db.Column(db.String(100))
    difficulty = db.Column(db.String(10))


class Option(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    image_path = db.Column(db.String(255))
    is_correct = db.Column(db.Boolean, default=False, nullable=False)

    question = db.relationship('Question', backref=db.backref('options', lazy=True, cascade='all, delete-orphan'))


class Attempt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    finished_at = db.Column(db.DateTime)
    score = db.Column(db.Integer, default=0)

    test = db.relationship('Test', backref=db.backref('attempts', lazy=True))
    student = db.relationship('Student', backref=db.backref('attempts', lazy=True))


class AttemptAnswer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    attempt_id = db.Column(db.Integer, db.ForeignKey('attempt.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    option_id = db.Column(db.Integer, db.ForeignKey('option.id'), nullable=False)

    attempt = db.relationship('Attempt', backref=db.backref('answers', lazy=True, cascade='all, delete-orphan'))
    question = db.relationship('Question')
    option = db.relationship('Option')


class HomeworkSubmission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    text = db.Column(db.Text)
    file_path = db.Column(db.String(300))
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    score = db.Column(db.Integer)

    test = db.relationship('Test', backref=db.backref('homework_submissions', lazy=True, cascade='all, delete-orphan'))
    student = db.relationship('Student')


class AIQuestion(db.Model):
    __tablename__ = 'ai_question'
    id = db.Column(db.Integer, primary_key=True)
    text = db.Column(db.String(500), nullable=False)

    answers = db.relationship('AIAnswer', backref='question', lazy=True, cascade='all, delete-orphan')


class AIAnswer(db.Model):
    __tablename__ = 'ai_answer'
    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('ai_question.id'), nullable=False)
    text = db.Column(db.String(500), nullable=False)
    # JSON with weights per ENT combination, e.g. {"math_inf":3,"math_phys":1}
    scores = db.Column(db.JSON, nullable=False, default=dict)


class AIResult(db.Model):
    __tablename__ = 'ai_result'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    scores = db.Column(db.JSON, nullable=False, default=dict)
    top_combinations = db.Column(db.JSON, nullable=False, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id])



