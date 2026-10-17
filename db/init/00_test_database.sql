-- Banco separado para os testes automatizados (nunca usamos o banco real nos testes).
CREATE DATABASE IF NOT EXISTS hackathon_test CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON hackathon_test.* TO 'hackathon'@'%';
FLUSH PRIVILEGES;
