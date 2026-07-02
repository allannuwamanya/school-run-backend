import secrets
import string

# Define the characters to choose from
alphabet = string.ascii_letters + string.digits + string.punctuation

# Generate a 50-character random key
secret_key = ''.join(secrets.choice(alphabet) for i in range(50))

print(secret_key)