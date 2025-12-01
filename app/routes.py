from flask import Flask, render_template

app = Flask(__name__)

# Esta é a rota vazia ou rota raiz
@app.route('/')
def index():
    # Renderiza o template que você usará para sua página inicial (ex: index.html)
    return render_template('index.html') 

# Exemplo de uma rota de boas-vindas simples sem template
@app.route('/ola')
def ola_mundo():
    return 'Olá Mundo, esta é uma rota simples!'

if __name__ == '__main__':
    app.run(debug=True)