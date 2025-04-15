FROM alpine:latest

RUN apk add --no-cache samba samba-common-tools

RUN adduser -D ocr && echo -e "ocr\nocr" | smbpasswd -a -s ocr && \
    adduser -D appuser && echo -e "appuser\nappuser" | smbpasswd -a -s appuser

RUN mkdir -p /shares/Scans && \
    chown -R ocr:ocr /shares/Scans && \
    chmod -R 0775 /shares/Scans && \
    setfacl -m u:ocr:rwx /shares/Scans && \
    setfacl -m u:appuser:rwx /shares/Scans

RUN ln -sf /dev/stdout /var/log/samba/log.smbd && \
    ln -sf /dev/stderr /var/log/samba/log.nmbd

COPY smb.conf /etc/samba/smb.conf

EXPOSE 137/udp 138/udp 139/tcp 445/tcp

CMD ["smbd", "-F", "--no-process-group"]