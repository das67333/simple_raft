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

# disable follower 1
echo 'DISABLE FOLLOWER'
curl -X POST -L "http://127.0.0.1:50021/disable"
sleep 1

# update
echo 'UPDATE hello'
curl -X PUT -L "http://127.0.0.1:50020/data/0" -H "Content-Type: application/json" -d '{"value": "hello"}'
sleep 1

read_all

# enable follower 1
echo 'ENABLE FOLLOWER'
curl -X POST -L "http://127.0.0.1:50021/enable"
sleep 1

# cas
echo 'CAS (SUCCESS) hello -> hola'
curl -X PUT -L "http://127.0.0.1:50020/data/0/cas" -H "Content-Type: application/json" -d '{"value": "hola", "old_value": "hello"}'
sleep 1

read_all
