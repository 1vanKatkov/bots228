# Настройка Git для работы с Amvera

Инструкция по настройке аутентификации для работы с Git репозиторием Amvera.

## Проблема: Authentication failed

Если вы получаете ошибку:
```
fatal: Authentication failed for 'https://git.msk0.amvera.ru/...'
```

Это означает, что Git не может аутентифицироваться для доступа к репозиторию.

## Решения

### Решение 1: Использование SSH (рекомендуется)

#### Шаг 1: Проверьте наличие SSH ключа

```bash
# Проверьте существующие ключи
ls -al ~/.ssh
```

Если ключей нет, создайте новый:

```bash
# Windows (Git Bash или PowerShell)
ssh-keygen -t ed25519 -C "your_email@example.com"

# Или используйте RSA
ssh-keygen -t rsa -b 4096 -C "your_email@example.com"
```

Нажмите Enter для всех вопросов (или укажите пароль для ключа).

#### Шаг 2: Скопируйте публичный ключ

**Windows (PowerShell):**
```powershell
Get-Content ~/.ssh/id_ed25519.pub
# или
Get-Content ~/.ssh/id_rsa.pub
```

**Windows (Git Bash):**
```bash
cat ~/.ssh/id_ed25519.pub
# или
cat ~/.ssh/id_rsa.pub
```

Скопируйте весь вывод (начинается с `ssh-ed25519` или `ssh-rsa`).

#### Шаг 3: Добавьте ключ в Amvera

1. Войдите в личный кабинет Amvera
2. Перейдите в "Настройки" → "SSH ключи" или "Профиль" → "SSH Keys"
3. Нажмите "Добавить SSH ключ"
4. Вставьте скопированный публичный ключ
5. Сохраните

#### Шаг 4: Клонируйте через SSH

Используйте SSH URL вместо HTTPS:

```bash
# Вместо:
# git clone https://git.msk0.amvera.ru/overmotivated/astrolhub

# Используйте:
git clone git@git.msk0.amvera.ru:overmotivated/astrolhub.git
```

---

### Решение 2: Использование токена доступа (HTTPS)

#### Шаг 1: Создайте токен доступа в Amvera

1. Войдите в личный кабинет Amvera
2. Перейдите в "Настройки" → "Токены доступа" или "Access Tokens"
3. Создайте новый токен:
   - Название: `git-access` (или любое другое)
   - Права: выберите `read` и `write` для репозиториев
   - Срок действия: выберите нужный период
4. **ВАЖНО**: Скопируйте токен сразу! Он больше не будет показан.

#### Шаг 2: Используйте токен при клонировании

**Вариант A: В URL (небезопасно, но быстро)**

```bash
git clone https://YOUR_TOKEN@git.msk0.amvera.ru/overmotivated/astrolhub.git
```

Замените `YOUR_TOKEN` на ваш токен.

**Вариант B: Через Git Credential Manager (рекомендуется)**

При клонировании Git запросит учетные данные:

```bash
git clone https://git.msk0.amvera.ru/overmotivated/astrolhub.git
```

Когда запросит:
- **Username**: ваш логин Amvera (или `overmotivated`)
- **Password**: вставьте токен доступа (не пароль!)

**Вариант C: Настройка через Git config**

```bash
# Сохраните учетные данные
git config --global credential.helper store

# При следующем клонировании введите токен как пароль
git clone https://git.msk0.amvera.ru/overmotivated/astrolhub.git
```

---

### Решение 3: Использование учетных данных Amvera (если поддерживается)

Если Amvera позволяет использовать обычный пароль:

```bash
git clone https://your_username:your_password@git.msk0.amvera.ru/overmotivated/astrolhub.git
```

**⚠️ ВНИМАНИЕ**: Это небезопасно! Пароль будет виден в истории команд.

---

## Настройка для Windows

### Использование Windows Credential Manager

Windows автоматически сохраняет учетные данные через Credential Manager:

1. При первом клонировании введите:
   - Username: ваш логин Amvera
   - Password: токен доступа

2. Windows сохранит их автоматически

3. Для просмотра/удаления:
   - Откройте "Панель управления" → "Учетные данные Windows"
   - Найдите запись для `git.msk0.amvera.ru`

### Использование Git Credential Manager

```bash
# Установите Git Credential Manager (обычно уже установлен с Git)
git config --global credential.helper manager-core

# Теперь при клонировании введите токен как пароль
```

---

## Проверка подключения

### Проверка SSH подключения

```bash
ssh -T git@git.msk0.amvera.ru
```

Должно вернуть сообщение об успешной аутентификации.

### Проверка HTTPS подключения

```bash
git ls-remote https://git.msk0.amvera.ru/overmotivated/astrolhub.git
```

Если запросит пароль, введите токен доступа.

---

## Работа с существующим репозиторием

Если вы уже клонировали репозиторий и нужно изменить URL:

### Изменить URL на SSH

```bash
cd astrolhub
git remote set-url origin git@git.msk0.amvera.ru:overmotivated/astrolhub.git
```

### Изменить URL на HTTPS с токеном

```bash
cd astrolhub
git remote set-url origin https://YOUR_TOKEN@git.msk0.amvera.ru/overmotivated/astrolhub.git
```

### Проверить текущий URL

```bash
git remote -v
```

---

## Частые проблемы

### Проблема: "Permission denied (publickey)"

**Решение:**
1. Убедитесь, что SSH ключ добавлен в Amvera
2. Проверьте правильность SSH URL
3. Проверьте права доступа к файлу ключа:
   ```bash
   chmod 600 ~/.ssh/id_ed25519
   ```

### Проблема: "Repository not found"

**Решение:**
1. Проверьте правильность пути к репозиторию
2. Убедитесь, что у вас есть доступ к репозиторию
3. Проверьте права токена доступа

### Проблема: Токен не работает

**Решение:**
1. Убедитесь, что используете токен как пароль, а не логин
2. Проверьте срок действия токена
3. Создайте новый токен с правильными правами

### Проблема: Windows не сохраняет учетные данные

**Решение:**
```bash
# Очистите сохраненные учетные данные
git credential-manager-core erase
host=git.msk0.amvera.ru
protocol=https

# Или через Windows Credential Manager
# Панель управления → Учетные данные Windows → Удалите запись для git.msk0.amvera.ru
```

---

## Рекомендации по безопасности

1. ✅ **Используйте SSH ключи** вместо паролей
2. ✅ **Используйте токены доступа** с ограниченными правами
3. ✅ **Не коммитьте токены** в репозиторий
4. ✅ **Используйте разные токены** для разных проектов
5. ✅ **Регулярно обновляйте токены**
6. ❌ **Не используйте пароли в URL**
7. ❌ **Не делитесь токенами**

---

## Быстрое решение для вашего случая

Если нужно быстро клонировать репозиторий:

1. **Создайте токен доступа** в Amvera (Настройки → Токены доступа)

2. **Клонируйте с токеном:**
   ```bash
   git clone https://YOUR_TOKEN@git.msk0.amvera.ru/overmotivated/astrolhub.git
   ```

3. **Или используйте интерактивный режим:**
   ```bash
   git clone https://git.msk0.amvera.ru/overmotivated/astrolhub.git
   # Username: overmotivated (или ваш логин)
   # Password: вставьте токен доступа
   ```

---

## Дополнительная помощь

Если проблема не решена:

1. Проверьте документацию Amvera: https://docs.amvera.ru
2. Обратитесь в поддержку Amvera
3. Убедитесь, что у вас есть доступ к репозиторию `astrolhub`
