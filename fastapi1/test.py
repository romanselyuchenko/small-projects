import datetime

expiry = datetime.datetime.now() + datetime.timedelta(hours=1)
print("Токен истекает:", expiry)

now = datetime.datetime.now()
print(expiry - now)
# Проверка
if datetime.datetime.now() > expiry:
    print("Токен просрочен")
else:
    print("Токен ещё жив")
