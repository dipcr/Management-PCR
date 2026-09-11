from app.setup import bootstrap_admin

# Create the first Admin from ADMIN_EMAIL/ADMIN_PASSWORD, this is also seen in local dev, but this ones for 
# WSGI
bootstrap_admin()

from app import app

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
