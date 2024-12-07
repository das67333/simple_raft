read_all() {
    echo 'READ'
    curl -X GET -L "http://127.0.0.1:50020/data/0"
    curl -X GET -L "http://127.0.0.1:50021/data/0"
    curl -X GET -L "http://127.0.0.1:50022/data/0"
}


# create
echo 'CREATE hi'
curl -X POST -L "http://127.0.0.1:50020/data" -H "Content-Type: application/json" -d '{"value": "hi"}'
sleep 1

read_all

# disable leader
echo 'DISABLE LEADER'
curl -X POST -L "http://127.0.0.1:50020/disable"
echo -n 'Enter leader ID: '
read ID

# update
echo 'UPDATE hello'
curl -X PUT -L "http://127.0.0.1:5002$ID/data/0" -H "Content-Type: application/json" -d '{"value": "hello"}'
sleep 1

read_all

# enable old leader
echo 'ENABLE (OLD) LEADER'
curl -X POST -L "http://127.0.0.1:50020/enable"
sleep 1

# cas
echo 'CAS (SUCCESS) hello -> hola'
curl -X PUT -L "http://127.0.0.1:5002$ID/data/0/cas" -H "Content-Type: application/json" -d '{"value": "hola", "old_value": "hello"}'
sleep 1

read_all
