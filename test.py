import sqlite3

def hello(address, name, vendor, company, manufacture, updated_at, classic_major_class, classic_minor_class):
    print(address, name)

conn = sqlite3.connect('/home/pi/projects/sources/blue_hydra/blue_hydra.db')
conn.create_function("hello", 8, hello)
cur = conn.cursor()
cur.execute("DROP TRIGGER IF EXISTS tt;")
#cur.execute("CREATE TRIGGER tt AFTER INSERT|UPDATE ON blue_hydra_devices \
#                 BEGIN SELECT hello(NEW.address, \
#                                     NEW.name, \
#                                     NEW.vendor, \
#                                     NEW.company, \
#                                     NEW.manufacturer, \
#                                     NEW.updated_at, \
#                                     NEW.classic_major_class, \
#                                     NEW.classic_minor_class); \
#                  END;")

#cur.execute("UPDATE blue_hydra_devices \
#             SET name='test3' \
#             where address = '25:23:79:22:A0:7E';")

conn.close()
