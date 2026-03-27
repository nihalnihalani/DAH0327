import os
from flask import Flask, redirect, request, render_template, url_for
from auth import auth0

app = Flask(__name__)
app.secret_key = os.environ.get('AUTH0_SECRET')


@app.route('/')
async def index():
    session = await auth0.get_session()
    return render_template('index.html', session=session)


@app.route('/login')
async def login():
    url = await auth0.start_interactive_login()
    return redirect(url)


@app.route('/callback')
async def callback():
    await auth0.complete_interactive_login(request.url)
    return redirect(url_for('index'))


@app.route('/logout')
async def logout():
    url = await auth0.logout()
    return redirect(url)


@app.route('/profile')
async def profile():
    session = await auth0.get_session()
    if not session:
        return redirect(url_for('login'))
    return render_template('profile.html', user=session.get('user', {}))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
