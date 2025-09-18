from werkzeug.security import generate_password_hash

# Generate a proper password hash
password = "Jasmir@5276"
password_hash = generate_password_hash(password)

print(f"Password: {password}")
print(f"Hash: {password_hash}")

# Sample output will be something like:
# pbkdf2:sha256:600000$X4r2Jk8vL1qW9tR0$c2a7f...

