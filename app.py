import os
import re

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
#if not os.environ.get("API_KEY"):
#    raise RuntimeError("API_KEY not set")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    # Get the current user and their portfolio
    user_query = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])
    username = user_query[0].get("username")
    user = username.capitalize()
    stocks = db.execute("SELECT * FROM portfolios WHERE user = ? ORDER BY symbol", username)

    # Get current prices of stocks user owns
    current_prices = {}
    for stock in stocks:
        current_prices[stock.get("symbol")] = lookup(stock.get("symbol")).get("price")

    # Get current value of user's holdings in each stock
    total_prices = {}
    for stock in stocks:
        total_prices[stock.get("symbol")] = lookup(stock.get("symbol")).get("price") * stock.get("shares")

    # Get current value of all of the user's stocks
    holding_value = 0
    for kvp in total_prices:
        holding_value += total_prices.get(kvp)

    # Get user's current cash and total value of holdings + cash on account
    cash = db.execute("SELECT cash FROM users WHERE username = ?", username)[0].get("cash")
    grand_total = cash + holding_value

    return render_template("index.html", user=user, stocks=stocks, cash=cash, current_prices=current_prices, total_prices=total_prices, holding_value=holding_value, grand_total=grand_total)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)
        if request.form.get("shares").isnumeric() == False:
            return apology("must provide a valid number of shares", 400)

        # Lookup stock symbol
        info = lookup(request.form.get("symbol"))
        if info == None:
            return apology("must provide valid symbol", 400)
        shares = int(request.form.get("shares"))

        # Check how much cash the user has and gather the total cost of the shares they're trying to buy
        user_cash_query = db.execute("SELECT cash FROM users WHERE id = ?", session["user_id"])
        user_cash = user_cash_query[0].get("cash")
        price = float(info.get("price"))
        total = price * shares
        symbol = request.form.get("symbol")

        # Get the current user
        user_query = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])
        user = user_query[0].get("username")

        # Input purchase data into "transactions" table, update user cash
        if info != None and shares > 0:
            if user_cash > total:
                db.execute("INSERT INTO transactions (user, symbol, price, shares, transaction_type) VALUES (?, ?, ?, ?, ?)", user, symbol.upper(), price, shares, "buy")
                db.execute("UPDATE users SET cash = (cash - ?) WHERE id = ?", total, session["user_id"])

                # Input user, symbol, and shares into portfolios table, update if user already owns shares of that symbol
                query = db.execute("SELECT * FROM portfolios WHERE user = ? AND symbol = ?", user, symbol)
                if len(query) != 1:
                    db.execute("INSERT INTO portfolios (user, symbol, shares) VALUES (?, ?, ?)", user, symbol, shares)
                else:
                    db.execute("UPDATE portfolios SET shares = (shares + :shares) WHERE user = :user AND symbol = :symbol", user=user, symbol=symbol, shares=shares)

                return redirect("/")

            else:
                return apology("not enough cash, stranger", 400)
        else:
            return apology("must provide valid stock symbol", 400)

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    user_query = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])
    username = user_query[0].get("username")
    transactions = db.execute("SELECT * FROM transactions WHERE user = ? ORDER BY trans_time DESC", username)

    return render_template("history.html", transactions=transactions)

@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
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
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)

        # Lookup stock symbol
        info = lookup(request.form.get("symbol"))
        if info != None:
            return render_template("quoted.html", info=info, symbol=request.form.get("symbol").upper())
        else:
            return apology("must provide valid stock symbol", 400)

    return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        pw = request.form.get("password")
        if not pw:
            return apology("must provide password", 400)
        if pw != request.form.get("confirmation"):
            return apology("must confirm password", 400)
        if re.search("[0-9]", pw) == None or re.search("[A-Z]", pw) == None or re.search("\!|\@|\#|\$|\^|\&|\*|\(|\)|\-|\_|\=|\+|\;|\:|\`|\~", pw) == None or len(pw) < 8:
            return apology("must use password at least 8 characters long with a capital letter, digit, and special character", 400)

        # Check to see if username has been taken already
        query = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
        for name in query:
            if name["username"] == request.form.get("username"):
                return apology("that username is already taken", 400)

        # Register new user into the database
        db.execute("INSERT INTO users (username, hash) VALUES(?, ?)", request.form.get("username"), generate_password_hash(request.form.get("password"), method='plain', salt_length=8))

    return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # Get the current user and the stocks they own
    user_query = db.execute("SELECT username FROM users WHERE id = ?", session["user_id"])
    user = user_query[0].get("username")
    stocks = db.execute("SELECT symbol FROM portfolios WHERE user = ?", user)

    if request.method == "POST":
        # Ensure symbol and shares were submitted
        if not request.form.get("symbol"):
            return apology("must provide stock symbol", 400)
        if not request.form.get("shares"):
            return apology("must provide number of shares", 400)
        if request.form.get("shares").isnumeric() == False:
            return apology("must provide a valid number of shares", 400)

        # Lookup stock symbol
        info = lookup(request.form.get("symbol"))
        if info == None:
            return apology("must provide valid symbol", 400)
        shares = int(request.form.get("shares"))

        # Check how many shares the user owns
        query = db.execute("SELECT * FROM portfolios WHERE user = ? AND symbol = ?", user, request.form.get("symbol"))
        if len(query) != 1:
            return apology("you don't own this stock", 400)
        shares_num = query[0].get("shares")
        if shares_num < shares:
            return apology("you don't have enough shares to sell", 400)

        # Get the current stock price and calculate the total sell value
        price = float(info.get("price"))
        total = price * shares

        # Input sell data into "transactions" table, update user cash
        db.execute("INSERT INTO transactions (user, symbol, price, shares, transaction_type) VALUES (?, ?, ?, ?, ?)", user, request.form.get("symbol"), price, -shares, "sell")
        db.execute("UPDATE users SET cash = cash + ? WHERE id = ?", total, session["user_id"])

        # Update user shares in "portfolios" table
        if shares_num == shares:
            db.execute("DELETE FROM portfolios WHERE user = ? AND symbol = ?", user, request.form.get("symbol"))
        else:
            db.execute("UPDATE portfolios SET shares = (shares - :shares) WHERE user = :user AND symbol = :symbol", user=user, symbol=request.form.get("symbol"), shares=shares)

        return redirect("/")

    return render_template("sell.html", stocks=stocks)