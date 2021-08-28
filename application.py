import os

from datetime import datetime
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True


# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = True
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL(os.getenv("DATABASE_URL"))

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    #return render_template("index.html")
    stocks = db.execute("SELECT * FROM stocks WHERE user_id = ? AND shares > 0", session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])[0]["cash"]

    # add current price and total worth to dictionary
    for i in stocks:
        current_price = lookup(i["symbol"])["price"]
        i["current_price"] = current_price
        i["total"] = current_price * i["shares"]

    #calculate total worth
    total_worth = cash

    for i in range(len(stocks)):
        total_worth += stocks[i]["total"]

    return render_template("index.html", stocks = stocks, cash = cash, total_worth = total_worth)





@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "GET":
        return render_template("buy.html")

    else:
        symbol = request.form.get("symbol").upper()

        # verify ticker symbol
        if not lookup(symbol):
            flash("Not a valid ticker!")
            return render_template("buy.html")

        shares = request.form.get("shares")
        # verify user input
        try:
            shares = int(shares)

        except ValueError:
            return apology("Please enter a whole number.", 400)

        if shares < 1:
            return apology("Please enter 1 or more shares.", 400)



        stock_price = lookup(symbol)["price"]
        stock_name = lookup(symbol)["name"]
        transaction_cost = stock_price * int(shares)
        user_info = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])
        now = datetime.now()
        dt_string = now.strftime("%Y/%m/%d %H:%M:%S")

        # make sure user has enough capital
        if user_info[0]["cash"] < transaction_cost:
            flash("You don't have enough capital!")
            return render_template("buy.html")


        # check if user already has this stock and if so update amount
        stock_check = db.execute("SELECT * FROM stocks WHERE user_id = ? and symbol = ?", session["user_id"], symbol)

        # user does not already own this stock / add it
        if len(stock_check) == 0:
            db.execute("INSERT INTO stocks (user_id, symbol, shares, name) VALUES(?, ?, ?, ?)", session["user_id"], symbol, shares, stock_name)

            # add transactions to transaction history
            db.execute("INSERT INTO transactions (user_id, symbol, shares, cost, time) VALUES(?,?,?,?,?)", session["user_id"], symbol, shares, transaction_cost, dt_string)
            # update users cash amount
            db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", transaction_cost, session["user_id"])
            flash("Bought")
            return redirect("/")

        # user does already have this stock / update it
        if len(stock_check) != 0:
            db.execute("UPDATE stocks SET shares = shares + ? WHERE user_id = ? AND symbol = ?", shares, session["user_id"], symbol)
            db.execute("INSERT INTO transactions (user_id, symbol, shares, cost, time) VALUES(?,?,?,?,?)", session["user_id"], symbol, shares, transaction_cost, dt_string)
            # update users cash amount
            db.execute("UPDATE users SET cash = cash - ? WHERE id = ?", transaction_cost, session["user_id"])
            flash("Bought")
            return redirect("/")




@app.route("/history")
@login_required
def history():
    """Show history of transactions"""
    # get transaction history
    stocks = db.execute("SELECT * FROM transactions WHERE user_id = ?", session["user_id"])
    return render_template("history.html", stocks = stocks)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            flash("Must provide username.")
            return render_template("login.html")

        # Ensure password was submitted
        elif not request.form.get("password"):
            flash("Must provide password.")
            return render_template("login.html")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        flash("You have been successfully logged in.")
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    flash("Logged out.")
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "GET":
        return render_template("quote.html")

    else:
        symbol = request.form.get("symbol")
        if not symbol:
            flash("Please enter a valid ticker.")
            return render_template("quote.html")

        stock_info = lookup(symbol)
        if not stock_info:
            flash("No stock with that ticker has been found.")
            return render_template("quote.html")


        flash("You have been quoted!")
        return render_template("quoted.html", stock_info = stock_info)


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register User"""

    if request.method == "GET":
        return render_template("register.html")

    else:
        # make sure user provides username and password
        if not request.form.get("username"):
            flash("Must provide username.")
            return render_template("register.html")

        if not request.form.get("password"):
            flash("Must provide a password.")
            return render_template("register.html")

        # confirm passwords match
        if request.form.get("password") != request.form.get("confirmation"):
            flash("Passwords did not match.")
            return render_template("register.html")

        # confirm uniqueness of username
        check_username = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        if len(check_username) > 0:
            flash("Username is taken.")
            return render_template("register.html")

        # insert into SQL db
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password")))

        return redirect("/login")



@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():

    if request.method == "GET":
        stocks = db.execute("SELECT symbol FROM stocks WHERE user_id = ? AND shares > 0", session["user_id"])
        return render_template("sell.html", stocks=stocks)

    else:
        shares_to_sell = request.form.get("shares")
        symbol = request.form.get("symbol")
        sell_amount = int(shares_to_sell) * lookup(symbol)["price"]
        stock_info = db.execute("SELECT * FROM stocks WHERE user_id = ? AND symbol = ?", session["user_id"], symbol)
        now = datetime.now()
        dt_string = now.strftime("%Y/%m/%d %H:%M:%S")

        # make sure user has the amount of shares requested to sell
        if stock_info[0]["shares"] < int(shares_to_sell):
            flash("You don't have that many shares.")
            return redirect("/sell")

        else:
            db.execute("UPDATE stocks SET shares = shares - ? WHERE user_id = ? and symbol = ?", shares_to_sell, session["user_id"], symbol)
            db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", sell_amount, session["user_id"])
            db.execute("INSERT INTO transactions (user_id, symbol, shares, cost, time) VALUES(?,?,?,?,?)", session["user_id"], symbol, f'-{shares_to_sell}', sell_amount, dt_string)
            flash("Sold")
            return redirect("/")


def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
