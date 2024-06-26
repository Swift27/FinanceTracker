from tracker import app, db
from tracker.models import User, Transaction, Category
from flask import render_template, redirect, url_for, flash, request, jsonify
from tracker.forms import RegisterForm, LoginForm, TransactionForm, CategoryForm, DeleteTransactionForm, FilterForm
from flask_login import login_user, logout_user, login_required, current_user
from sqlalchemy import func, and_, extract
from datetime import datetime, timedelta

from tracker import app
from tracker.forms import TransactionHistoryForm

@app.route('/', methods=["GET", "POST"])
@app.route('/home', methods=["GET", "POST"])
@login_required
def home_page():
    transaction_form = TransactionForm()
    category_form = CategoryForm()
    delete_transaction_form = DeleteTransactionForm()
    filter_form = FilterForm()

    if "submit_transaction" in request.form and transaction_form.validate_on_submit():
        transaction_to_create = Transaction(name=transaction_form.name.data,
                                    type=transaction_form.type.data,
                                    category=transaction_form.category.data,
                                    amount=transaction_form.amount.data,
                                    date=transaction_form.date.data,
                                    user_id=current_user.user_id)
        db.session.add(transaction_to_create)

        if transaction_form.type.data == "Expense":
            current_user.expenses += float(transaction_form.amount.data)
        else:
            current_user.income += float(transaction_form.amount.data)

        db.session.commit()
        flash(f'Transaction "{transaction_to_create.name}" added successfully!', category='success')
        return redirect(url_for('home_page'))

    if transaction_form.errors != {}:
        for err_msg in transaction_form.errors.values():
            flash(err_msg[0], category="danger")

    # Start with a base query
    query = Transaction.query.filter_by(user_id=current_user.user_id)

    # If the form validates, add filters based on the form data
    if filter_form.validate_on_submit():
        if filter_form.type.data and filter_form.type.data != "All":
            query = query.filter(Transaction.type == filter_form.type.data)
        if filter_form.date.data:
            query = query.filter(extract('year', Transaction.date) == filter_form.date.data.year,
                                 extract('month', Transaction.date) == filter_form.date.data.month,
                                 extract('day', Transaction.date) == filter_form.date.data.day)
        if filter_form.category.data and filter_form.category.data != "All":
            query = query.filter(Transaction.category == filter_form.category.data)
        if filter_form.price.data:
            query = query.filter(Transaction.amount_rounded == filter_form.price.data)

    # Execute the query to get the transactions
    transactions = query.all()

    if filter_form.errors != {}:
        for err_msg in filter_form.errors.values():
            flash("Filter: " + err_msg[0], category="danger")

    return render_template('home.html',
                           transactions=transactions,
                           transaction_form=transaction_form,
                           category_form=category_form,
                           delete_transaction_form=delete_transaction_form,
                           filter_form=filter_form)

@app.route('/statistics', methods=["GET", "POST"])
@login_required
def statistics_page():
    transaction_history_form = TransactionHistoryForm()

    if transaction_history_form.validate_on_submit():
        return render_template('statistics.html',
                               transaction_history_form=transaction_history_form,
                               time_period=transaction_history_form.time_period.data)

    if transaction_history_form.errors != {}:
        for err_msg in transaction_history_form.errors.values():
            flash(err_msg[0], category="danger")

    return render_template('statistics.html',
                           transaction_history_form=transaction_history_form,
                           time_period='week')

@app.route('/register', methods=["GET", "POST"])
def register_page():
    register_form = RegisterForm()

    if register_form.validate_on_submit():
        user_to_create = User(username=register_form.username.data,
                              email_address=register_form.email_address.data,
                              password=register_form.password1.data)

        db.session.add(user_to_create)
        db.session.commit()
        login_user(user_to_create)
        flash(f'Account created successfully! You are now logged in as: {user_to_create.username}', category='success')
        return redirect(url_for('home_page'))

    if register_form.errors != {}:
        for err_msg in register_form.errors.values():
            flash(f'There was an error with creating the user: {err_msg}', category="danger")

    return render_template('register.html', register_form=register_form)

@app.route('/login', methods=["GET", "POST"])
def login_page():
    login_form = LoginForm()

    if login_form.validate_on_submit():
        attempted_user = User.query.filter_by(username=login_form.username.data).first()
        if not attempted_user:
            flash("Username does not exist!", category="danger")
            return redirect(url_for('login_page'))
        if not attempted_user.check_password_correction(attempted_password=login_form.password.data):
            flash("Incorrect password!", category="danger")
            return redirect(url_for('login_page'))

        login_user(attempted_user)
        return redirect(url_for('home_page'))

    return render_template('login.html', login_form=login_form)

@app.route('/logout', methods=["GET", "POST"])
def logout_page():
    logout_user()
    flash("You have been successfully logged out!", category="info")
    return redirect(url_for('login_page'))

@app.route('/api/expenses_by_category', methods=["GET"])
@login_required
def expenses_by_category():
    expenses = Transaction.query.filter_by(user_id=current_user.user_id, type="Expense").all()
    return jsonify([{"amount": expense.amount_rounded, "category": expense.category} for expense in expenses])

@app.route('/api/incomes_by_category', methods=["GET"])
@login_required
def incomes_by_category():
    incomes = Transaction.query.filter_by(user_id=current_user.user_id, type="Income").all()
    return jsonify([{"amount": income.amount_rounded, "category": income.category} for income in incomes])


@app.route('/api/transactions_over_time', methods=["GET"])
@login_required
def transactions_over_time():
    time_period = request.args.get('time_period', default='month', type=str)

    if time_period == 'month':
        start_date = datetime.now() - timedelta(days=30)
    elif time_period == 'week':
        start_date = datetime.now() - timedelta(weeks=1)
    else:
        start_date = datetime.now() - timedelta(days=365)

    transactions = db.session.query(
        func.date(Transaction.date).label('date'),
        func.sum(Transaction.amount_rounded).label('total'),
        Transaction.type
    ).filter(
        and_(
            Transaction.user_id == current_user.user_id,
            Transaction.date >= start_date
        )
    ).group_by(
        'date',
        Transaction.type
    ).all()

    # Initialize data for all dates within the selected time period
    data = {}
    current_date = start_date
    while current_date <= datetime.now():
        date_str = current_date.strftime('%Y-%m-%d')
        data[date_str] = {'income': 0, 'expense': 0}
        current_date += timedelta(days=1)

    # Update data with actual transaction totals
    for transaction in transactions:
        transaction_date_object = datetime.strptime(transaction.date, '%Y-%m-%d')
        date = transaction_date_object.strftime('%Y-%m-%d')
        if transaction.type == 'Income':
            data[date]['income'] = transaction.total
        else:
            data[date]['expense'] = transaction.total

    return jsonify(data)

@app.route('/api/total_values', methods=["GET"])
@login_required
def total_values():
    total_income = db.session.query(func.sum(Transaction.amount_rounded)).filter_by(user_id=current_user.user_id, type="Income").scalar()
    total_expenses = db.session.query(func.sum(Transaction.amount_rounded)).filter_by(user_id=current_user.user_id, type="Expense").scalar()
    total_budget = round(total_income - total_expenses, 2)
    print(total_income, total_expenses, total_budget)
    return jsonify({"total_expenses": total_expenses, "total_income": total_income, "total_budget": total_budget})

@app.route('/delete_transaction', methods=['POST'])
def delete_transaction():
    transaction_id = request.form.get('deleted_transaction')
    transaction = Transaction.query.get(transaction_id)
    if transaction:
        db.session.delete(transaction)
        db.session.commit()
    else:
        flash("Transaction not found!", category="danger")
    return redirect(url_for('home_page'))

@app.route('/add_category', methods=['POST'])
def add_category():
    try:
        category_name = request.form.get('category_name')
        print(category_name)
        if not category_name:
            flash("Category name not provided!", category="danger")
        elif Category.query.filter_by(name=category_name, user_id=current_user.user_id).first():
            flash("Category already exists. Please choose a different category name.", category="danger")
        else:
            category_to_create = Category(name=category_name, user_id=current_user.user_id)
            db.session.add(category_to_create)
            db.session.commit()
            flash(f'Category "{category_to_create.name}" added successfully!', category='success')
    except:
        flash("An error occured adding the category.", category="danger")
    return redirect(url_for('home_page'))