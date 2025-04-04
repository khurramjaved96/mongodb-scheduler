start = 0
elem = 50


low = start
high = start + elem -1
priority = 5
import random



command = "./Count --config ../configs/BreakoutLong.json  --run "
directory = "/Users/kjaved/Code/keen/kjaved/streaming_drl/build"
query = "[ "
for i in range(low, high):
    query+='{ "command" : "' + command + str(i) + '"' +  ', "priority" : ' + str(priority) +', "rand" : '+ str(random.randint(0, 9000000)) +', "status" : 0, "directory" : "' + directory + '"},\n'


query += '{ "command" : "' + command + str(high) + '"' +  ', "priority" : ' + str(priority) +', "rand" : '+ str(random.randint(0, 9000000)) +', "status" : 0, "directory" : "' + directory + '"}]'

print(query)




