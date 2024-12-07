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

# update
echo 'UPDATE hello'
curl -X PUT -L "http://127.0.0.1:50020/data/0" -H "Content-Type: application/json" -d '{"value": "hello"}'
sleep 1

read_all

# cas
echo 'CAS (FAILURE) hi -> hola'
curl -X PUT -L "http://127.0.0.1:50020/data/0/cas" -H "Content-Type: application/json" -d '{"value": "hola", "old_value": "hi"}'
sleep 1

read_all

echo 'CAS (SUCCESS) hello -> hola'
curl -X PUT -L "http://127.0.0.1:50020/data/0/cas" -H "Content-Type: application/json" -d '{"value": "hola", "old_value": "hello"}'
sleep 1

read_all

# delete
echo 'DELETE hola'
curl -X DELETE -L "http://127.0.0.1:50020/data/0"
sleep 1

read_all
