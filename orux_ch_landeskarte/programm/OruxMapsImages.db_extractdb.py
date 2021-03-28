"""
  Dieses Script extrahiert alle Images aus 'Hombrechtikon.otrk2.xml'
"""
import sqlite3
import sys

db = sqlite3.connect("OruxMapsImages.db")
c = db.cursor()
c.execute("select x, y, z, image from tiles")
for row in c:
    x = row[0]
    y = row[1]
    z = row[2]
    image = row[3]
    open(f"{x:03d}-{y:03d}-{z:03d}.jpg", "wb").write(image)

sys.stdin.readline()
