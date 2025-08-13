#!/bin/bash

# unfortunately the arguments are slightly different for the US EAST region
if [ "$REGION" != "us-east-1" ]; then
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_UPLOAD" --create-bucket-configuration LocationConstraint="$REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_INCOMING" --create-bucket-configuration LocationConstraint="$REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_FILES" --create-bucket-configuration LocationConstraint="$REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_CATEGORIZED" --create-bucket-configuration LocationConstraint="$REGION"
else
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_UPLOAD --region $REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_INCOMING --region $REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_FILES --region $REGION"
  awslocal s3api create-bucket --bucket "$BUCKET_NAME_CATEGORIZED --region $REGION"
fi

awslocal secretsmanager create-secret --name "lambda/pull/bank1" --secret-string file:///generated/keys/id_rsa --region $REGION
awslocal secretsmanager create-secret --name "lambda/pull/peer1" --secret-string file:///generated/keys/id_rsa --region $REGION
awslocal secretsmanager create-secret --name "lambda/api/wise" --secret-string '{}' --region $REGION
awslocal secretsmanager create-secret --name "lambda/rotate/marble.arch/arch/auth" --secret-string '{}' --region $REGION
awslocal secretsmanager create-secret --name "lambda/on_upload/pgp/bank1" --secret-string '{}' --region $REGION