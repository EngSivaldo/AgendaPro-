# 🚀 AgendaPro - Sistema de Agendamento Dinâmico em Flask

Este é um sistema web completo desenvolvido em Python com o framework **Flask** para gerenciar agendamentos, usuários e serviços. Ideal para pequenos negócios, salões de beleza, clínicas ou qualquer serviço que exija marcação de horários.

## ✨ Funcionalidades Principais

- **Autenticação Completa:** Cadastro e Login de Clientes e Administradores (**Flask-Login**).
- **Gestão de Usuários:** Dashboard exclusivo para administradores com listagem, edição (nome, email, permissão) e deleção de usuários.
- **Gestão de Serviços:** Rotas preparadas para listar, adicionar e configurar serviços disponíveis.
- **Linha de Comando (CLI):** Comando customizado `flask create-admin` para criação rápida e segura de administradores no terminal.
- **Segurança:** Uso de decoradores (`@admin_required`) para proteger rotas administrativas.

## 🛠️ Tecnologias Utilizadas

- **Backend:** Python 3.x, **Flask**
- **Banco de Dados:** **SQLAlchemy** (ORM) sobre SQLite (padrão de desenvolvimento)
- **Segurança:** **Flask-Login** (Autenticação de Sessão) e **Werkzeug** (Hashing de Senhas)
- **Frontend:** HTML5, CSS3, **Bootstrap 5** (para responsividade e estilo)

## ⚙️ Configuração e Instalação

Siga estes passos para configurar e rodar o projeto em sua máquina local.

### Pré-requisitos

- Python 3.8+
- pip (gerenciador de pacotes do Python)

### 1. Clonar o Repositório

```bash
git clone [https://github.com/seuusuario/agendapro.git](https://github.com/seuusuario/agendapro.git)
cd agendapro
```

# Cria o ambiente

python -m venv venv

# Ativa o ambiente (Windows)

.\venv\Scripts\activate

# Ativa o ambiente (Linux/macOS)

source venv/bin/activate

pip install -r requirements.txt

# Formato: flask create-admin "Nome do Admin" email@admin.com sua_senha_forte

flask create-admin "Master Admin" admin@agendapro.com SenhaSegura123

python run.py

Rota,Descrição,Acesso Requerido
/,Página Inicial,Público
/auth/register,Cadastro de Clientes,Público
/auth/login,Login de Usuários,Público
/services/dashboard,Painel de Administração,Administrador
/auth/manage_users,Gerenciamento de Usuários,Administrador

Seu Nome [Seu Email] [Link do seu GitHub]
