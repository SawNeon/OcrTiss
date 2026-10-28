# Subir na VPS

Instruções para a VPS que já hospeda `app.legacydoc.com.br`
(2 vCore, 4 GB de RAM, 30 GB de disco).

O serviço escuta apenas em `127.0.0.1:8077`; quem atende a internet é o nginx
que já está na máquina.

## 1. Clonar e configurar

```bash
cd /opt
sudo git clone https://github.com/SawNeon/OcrTiss.git tiss-ocr
sudo chown -R $USER:$USER tiss-ocr
cd tiss-ocr

cp .env.producao.example .env
nano .env     # defina AUTH_USER e AUTH_PASSWORD
```

**Sem `AUTH_USER` e `AUTH_PASSWORD` a tela fica aberta para quem souber o
endereço.** O serviço avisa no log quando sobe desprotegido.

## 2. Subir

```bash
docker compose up -d --build
docker compose logs -f        # acompanhe até "Application startup complete"
curl -u atendente:SUA_SENHA http://127.0.0.1:8077/api/health
```

A primeira construção leva alguns minutos: compila o front e instala OpenCV,
numpy e scikit-learn.

## 3. Publicar no domínio

Crie o subdomínio `ocr.legacydoc.com.br` apontando para o IP da VPS e adicione
um site no nginx:

```nginx
server {
    server_name ocr.legacydoc.com.br;

    # Guias chegam como PDF ou foto; o padrão do nginx (1 MB) rejeitaria.
    client_max_body_size 30M;

    location / {
        proxy_pass http://127.0.0.1:8077;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # Uma página leva de 6 a 20 segundos para ser lida.
        proxy_read_timeout 120s;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/ocr /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d ocr.legacydoc.com.br
```

O certificado não é opcional: a senha do acesso básico trafega em texto claro
sem HTTPS.

## 4. Carregar o cadastro de cooperados

A planilha não vai no repositório. Envie e importe:

```bash
scp COOPERADO.xlsx usuario@vps:/tmp/
docker compose cp /tmp/COOPERADO.xlsx tiss-ocr:/tmp/
docker compose exec tiss-ocr python scripts/import_professionals.py /tmp/COOPERADO.xlsx --uf MG
docker compose exec tiss-ocr rm /tmp/COOPERADO.xlsx
```

## 5. Atualizar depois

```bash
cd /opt/tiss-ocr
git pull
docker compose up -d --build
```

O volume `tiss-var` preserva o cadastro e o histórico de correções entre
atualizações.

## Recursos

Com 2 vCore e 4 GB dividindo com o legacydoc, o compose limita este serviço a
1,5 CPU e 2 GB. Em repouso ele ocupa por volta de 400 MB; a leitura de uma
página usa um núcleo por alguns segundos. A imagem ocupa cerca de 1,2 GB em
disco.

## Antes de mostrar a alguém

- **Use guias sintéticas na apresentação.** `scripts/generate_synthetic_dataset.py`
  gera guias com dados fictícios. Guia real traz dado de paciente, e o servidor
  é compartilhado.
- **Deixe `LLM_FALLBACK_ENABLED=false`** enquanto a decisão de compliance não
  estiver tomada: ligado, a imagem da guia vai para a OpenAI.
- Os arquivos enviados ficam no volume por 24 horas e são descartados no
  próximo start.

## O que ainda falta para uso real

Isto é um ambiente de demonstração. Para produção faltam: autenticação por
usuário em vez de senha única, fila para processar fora da requisição, banco
de dados no lugar do armazenamento em memória das extrações, backup do volume
e monitoramento.

O serviço roda com **um worker** por causa desse armazenamento em memória: com
dois processos, metade das correções bateria no worker que não conhece a
extração. Atender mais de um atendente em paralelo depende de mover esse
estado para o banco — o cadastro e o histórico já estão lá.
