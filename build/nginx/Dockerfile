# Use the Nginx image
FROM nginx:latest

#Remove the default nginx.conf
RUN rm /etc/nginx/conf.d/default.conf

#Replace with our own ngninx.conf
COPY nginx.conf /etc/nginx/conf.d


