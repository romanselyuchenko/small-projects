import csv


with open("ratings.csv", "r", encoding="utf-8", newline="") as source, \
        open("new.txt", "w", encoding="utf-8", newline="") as target:
    reader = csv.reader(source, delimiter=";")
    writer = csv.writer(target, delimiter=";", lineterminator="\n")

    for row in reader:
        if len(row) > 3 and "The Summary is " in row[3]:
            row[3] = row[3].split("The Summary is ", 1)[1]
        writer.writerow(row)