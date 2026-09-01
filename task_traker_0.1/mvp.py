# это версия без сохранения данных, дальше сделать с сохранением в файл, потом в бд 
from datetime import datetime


tasks_list = [
                    {'date': datetime(2026, 6, 27, 23, 0),
                'id': 1},
                    {'date': datetime(2026, 6, 28, 19, 0),
                'id': 2},
                    {'date': datetime(2026, 6, 29, 9, 0),
                'id': 3},
                    {'date': datetime(2026, 6, 30, 9, 0),
                'id': 4},
                    {'date': datetime(2026, 6, 29, 9, 0),
                'id': 5},        
    ]
id = 6

time_now = datetime.now()

def appending(id):
    day, hour = input("Please enter the date and the hour of the deadline: ").split()
    specified_time = datetime(time_now.year, time_now.month, int(day), int(hour))
    # remaining_time = specified_time - time_now
    # r_hours = remaining_time.seconds // 3600

    task = {
        'date': specified_time,
        # 'remaining_time': f"days {remaining_time.days} hours {r_hours}", это не тут должно быть
        # 'text': task_text,
        'id': id

    }
    tasks_list.append(task)
    id += 1

def just_show_all():
    for task in tasks_list:
        print(f"{task['date'].day} {task['date'].strftime('%B')}")

def tasks_of_the_day(time: datetime)-> list:
    result = []

    for task in tasks_list:
        if task['date'] == time:
            result.append(task)

    return result

def display():
    unique_dates = []
    for date in sorted([i['date'].date() for i in tasks_list]):
        if date not in unique_dates:
            unique_dates.append(date)
    
    
    for time in sorted([i['date'] for i in tasks_list]):
        if time.date() in unique_dates:
            print(f"{time.day} {time.strftime('%B')}")
            for task in tasks_of_the_day(time):
                print(f"Task: №{task['id']}")
            unique_dates.remove(time.date())


display()

