'''
  Dieses Script extrahiert alle Images aus 'Hombrechtikon.otrk2.xml'
'''
import sqlite3
import sys

db = sqlite3.connect('OruxMapsImages.db')
c = db.cursor()
c.execute('select x, y, z, image from tiles')
for row in c:
  x = row[0]
  y = row[1]
  z = row[2]
  image = row[3]
  open('%03d-%03d-%03d.jpg' % (x, y, z), 'wb').write(image)

sys.stdin.readline()