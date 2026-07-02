# Django REST Framework API Starter

This is a powerful and secure starter project for building RESTful APIs with Django. It comes pre-configured with a modern technology stack and essential features to get you up and running quickly.


## Features

* **Modern Authentication**: Uses **JSON Web Tokens (JWT)** for secure, stateless authentication (`djangorestframework-simplejwt`).
* **Custom User Model**: A flexible and extensible custom user model is ready from the start, using email as the primary identifier.
* **API Documentation**: Automatic, interactive API documentation powered by **Swagger (drf-yasg)**.
* **Environment-based Configuration**: All sensitive keys and settings are loaded from a `.env` file for better security.
* **Custom Management Commands**: Includes a command to create a superuser from environment variables, perfect for deployment.
* **Social Authentication Hooks**: Includes skeletons for Google and Facebook social authentication.
* **CORS Ready**: Pre-configured with `django-cors-headers` to allow frontend integrations.

## Getting Started

Follow these instructions to get the project set up and running on your local machine.

### Prerequisites

* Python 3.8+
* `virtualenv` (or another virtual environment tool)

### Installation and Setup

1.  **Clone the Project**
    ```bash
    git clone [https://github.com/morshedmasud/django-rest-framework-mysql-boilerplate.git](https://github.com/morshedmasud/django-rest-framework-mysql-boilerplate.git)
    cd django-rest-framework-mysql-boilerplate
    ```

2.  **Create and Activate a Virtual Environment**
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    *On Windows, use `venv\Scripts\activate`*

3.  **Install Dependencies**
    ```bash
    pip install -r requirements.txt
    ```

4.  **Set Up Environment Variables**

    Create a `.env` file in the project root by copying the example file:
    ```bash
    cp .env.example .env
    ```

    Now, open the `.env` file and fill in the required values. At a minimum, you need to generate a `SECRET_KEY`.

    **Generate a Secret Key:**
    You can generate a new secret key using the built-in Django utility:
    ```bash
    python generate_key.py
    ```
    Copy the output and paste it as the value for `SECRET_KEY` in your `.env` file.

    **Your `.env` file should look like this:**
    ```env
    # SECURITY
    SECRET_KEY=your_newly_generated_secret_key_here
    DEBUG=1
    ALLOWED_HOSTS=127.0.0.1,localhost

    # ADMIN USER CREDENTIALS
    ADMIN_EMAIL=admin@example.com
    ADMIN_PASSWORD=YourSecurePassword123

    # DATABASE (Defaults to SQLite)
    # DB_NAME=your_db
    # DB_USER=your_user
    # ...
    ```

5.  **Run Database Migrations**
    This will create the necessary database tables, including those for the custom user model.
    ```bash
    python manage.py migrate
    ```

6.  **Create a Superuser**
    This command will create an admin account using the credentials you set in your `.env` file.
    ```bash
    python manage.py create_super_user
    ```

7.  **Run the Development Server**
    ```bash
    python manage.py runserver
    ```
    The API will now be running at `http://127.0.0.1:8000/`.

## API Endpoints

Once the server is running, you can interact with the following key endpoints:

* **Admin Panel**: `http://127.0.0.1:8000/admin/`
* **API Documentation (Swagger)**: `http://127.0.0.1:8000/swagger/`

### Authentication Endpoints

* **Register a new user**:
    * `POST /api/register/`
    * Body: `{ "full_name": "John Doe", "email": "john.doe@example.com", "password": "yourpassword" }`
* **Obtain JWT Tokens**:
    * `POST /api/login/`
    * Body: `{ "email": "your_email", "password": "your_password" }`
    * **Returns**: An `access` and `refresh` token.
* **Refresh Access Token**:
    * `POST /api/login/refresh/`
    * Body: `{ "refresh": "your_refresh_token" }`

To access protected endpoints, include the access token in the request header:
`Authorization: Bearer <your_access_token>`