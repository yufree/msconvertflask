# ./Dockerfile (用于 Python/Flask 合并镜像方案)

# 步骤 1: 以 pwiz-skyline 镜像为基础
FROM chambm/pwiz-skyline-i-agree-to-the-vendor-licenses:3.0.25142-eb0d7d9

# 步骤 2: 切换到 root 用户进行安装
USER root

# 设置 DEBIAN_FRONTEND 避免交互式提示
ENV DEBIAN_FRONTEND=noninteractive
# 继承基础镜像的环境变量，并设置 WINEDEBUG
ENV WINEDEBUG="+warn,+fixme" 

# 步骤 3: 安装 Python, pip, Flask 和其他系统依赖
# 3.1 确保系统支持 i386架构 (基础镜像应已包含)
RUN dpkg --add-architecture i386 && \
    apt-get update && \
    # 尝试安装 wine32，如果失败则依赖基础镜像的 wine 设置
    (apt-get install -y --no-install-recommends wine32 || echo "wine32 package not found or not needed, relying on base image wine setup")

# 3.2 安装 Python 和 pip
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    python3 \
    python3-pip \
    python3-venv \ 
    sudo \         
    xvfb \         
    && \
    rm -rf /var/lib/apt/lists/*

# 步骤 4: 安装 Flask
# 我们将 Flask 安装到系统级别，也可以选择在虚拟环境中安装
RUN pip3 install Flask==2.3.3 Werkzeug==2.3.7 # 固定版本以提高稳定性

# 步骤 5: 创建一个非 root 用户来运行 Flask 应用 (更安全)
# 同时将此用户添加到 sudo 组，以便后续配置 sudoers
RUN useradd flask_user --create-home --shell /bin/bash --groups sudo || echo "User flask_user already exists or was already in sudo group."

# 步骤 6: 配置 sudoers
# 允许 flask_user 用户无密码以 root 身份运行 /usr/bin/env 命令。
# Python 脚本将使用 "sudo /usr/bin/env VAR=val command arg" 的形式。
RUN echo 'flask_user ALL=(root) NOPASSWD: /usr/bin/env' >> /etc/sudoers && \
    echo "Configured sudo for flask_user to run commands via /usr/bin/env as root."

# 步骤 7: 创建应用目录和共享数据目录
# 应用目录
RUN mkdir -p /app && chown -R flask_user:flask_user /app
# 共享数据目录 (上传和转换后的文件)
RUN mkdir -p /app/shared_data/uploads && \
    mkdir -p /app/shared_data/converted && \
    chown -R flask_user:flask_user /app/shared_data

# 步骤 8: 复制 Flask 应用文件
WORKDIR /app
COPY ./app.py /app/app.py
# 设置 app.py 和 templates 的所有者
RUN chown flask_user:flask_user /app/app.py && \
    ( [ -d /app/templates ] && chown -R flask_user:flask_user /app/templates || echo "No templates directory to chown." )


# 步骤 9: 切换到 flask_user 用户
USER flask_user

# 步骤 10: 暴露 Flask 应用端口
EXPOSE 5000

# 步骤 11: 定义容器启动时运行的命令
ENV FLASK_APP=app.py
ENV FLASK_ENV=development
# ENV FLASK_ENV=production
# 使用 gunicorn 或直接用 flask run (对于简单应用 flask run 也可以)
# CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
