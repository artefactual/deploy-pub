#!/usr/bin/env bash

set -o errexit
set -o nounset
set -o pipefail

ESHOST="http://192.168.100.100:9200"
ESINDEX="twitter"
ESTYPE="tweet"
ESBASE="$ESHOST/$ESINDEX/$ESTYPE"

# Delete index
curl -XDELETE "$ESHOST/$ESINDEX"
echo

# Create index
curl -XPUT "$ESHOST/$ESINDEX" -d '{
  "settings": {
    "number_of_shards": 3,
    "number_of_replicas": 2
  }
}'
echo

# Create type
curl -XPUT "$ESHOST/$ESINDEX/_mapping/$ESTYPE" -d '{
  "'$ESTYPE'": {
    "properties": {
      "message": {"type": "string", "store": true }
    }
  }
}'
echo

# Add documents
for i in {1..100}; do
  curl -XPUT "$ESBASE/$i" -d '{ "message": "Tweet '$i'" }'
  echo
done;

# Refresh index
curl -XPOST "$ESHOST/$ESINDEX/_refresh"
echo

# Show state
echo
echo "> -- Cluster health:"
curl -XGET "$ESHOST/_cat/health"
echo
echo "> -- Available nodes:"
curl -XGET "$ESHOST/_cat/nodes"
echo
echo "> -- Available indices:"
curl -XGET "$ESHOST/_cat/indices"

echo
